"""Stream the CRAS annotated scan (one huge ASCII zip member) into a small voxel-subsampled cache.

The member is never extracted or loaded whole: it is read in fixed-size byte blocks through
`zipfile`, parsed per block, and reduced to the first point (stream order) per voxel. Memory is
about 24 bytes per occupied voxel plus one block, not a function of the input point count.
The cache keeps xyz (float32, ~um precision for the lab's local metre coordinates), rgb (uint8)
and class (uint8); intensity is dropped.
"""

import io
import json
import zipfile
from pathlib import Path
from typing import Iterator

import numpy as np

MIN_PENDING = 2_000_000  # rows of deduped blocks buffered before the next consolidation
BITS = 21  # per voxel axis index; 2**21 cells (21 km at 1 cm)
OFFSET = 1 << (BITS - 1)
REPORT_EVERY = 1 << 30


def read_blocks(f, chunk_bytes: int) -> Iterator[bytes]:
    """Yield byte blocks of whole lines; the trailing partial line carries into the next block."""
    carry = b""
    while chunk := f.read(chunk_bytes):
        buf = carry + chunk
        cut = buf.rfind(b"\n") + 1
        carry = buf[cut:]
        if cut:
            yield buf[:cut]
    if carry.strip():
        yield carry


def voxel_keys(xyz: np.ndarray, voxel: float) -> np.ndarray:
    idx = np.floor(xyz / voxel).astype(np.int64) + OFFSET
    if idx.min() < 0 or idx.max() >= 1 << BITS:
        raise ValueError(f"voxel index out of range for voxel size {voxel}")
    return (idx[:, 0] << (2 * BITS)) | (idx[:, 1] << BITS) | idx[:, 2]


def _read_meta(path: Path) -> dict | None:
    try:
        with np.load(path) as d:
            return json.loads(str(d["meta"]))
    except (OSError, KeyError, ValueError):
        return None


def build_cache(zip_path, cache_path, voxel: float = 0.01, chunk_bytes: int = 64 << 20) -> dict:
    """Voxel-subsample the single member of `zip_path` into an `.npz` at `cache_path`."""
    cache_path = Path(cache_path)
    with zipfile.ZipFile(zip_path) as z:
        members = [i for i in z.infolist() if not i.is_dir()]
        if len(members) != 1:
            raise ValueError(f"expected one member in {zip_path}, found {len(members)}")
        info = members[0]

        old = _read_meta(cache_path) if cache_path.exists() else None
        if old and (old["voxel_size"], old["member"], old["member_size"]) == (voxel, info.filename, info.file_size):
            print(f"skip {cache_path} (up to date)")
            return old

        with z.open(info) as f:
            xyz, rgb, cls, read, declared = _stream(f, voxel, chunk_bytes)

    if read != declared:
        raise ValueError(f"read {read} points but the header declares {declared}; truncated or corrupt")
    meta = {
        "voxel_size": voxel,
        "member": info.filename,
        "member_size": info.file_size,
        "points_read": read,
        "points_declared": declared,
        "points_kept": len(xyz),
        "extent_min": xyz.min(axis=0).tolist(),
        "extent_max": xyz.max(axis=0).tolist(),
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_path.with_name(cache_path.name + ".tmp")
    with open(tmp, "wb") as out:
        np.savez(out, xyz=xyz, rgb=rgb, cls=cls, meta=json.dumps(meta))
    tmp.replace(cache_path)
    print(f"ok   {cache_path} ({len(xyz)} points)")
    return meta


def _consolidate(keys, parts, pending):
    """Fold pending (keys, xyz, rgb, cls) blocks into `keys` (sorted, unique) and the data `parts`.

    Earlier rows win; only rows whose voxel is new are appended, as one segment, never re-copied.
    """
    pk, xyz, rgb, cls = (np.concatenate(c) for c in zip(*pending))
    pk, first = np.unique(pk, return_index=True)  # stable: earlier rows win
    if len(keys):
        pos = np.minimum(np.searchsorted(keys, pk), len(keys) - 1)
        new = keys[pos] != pk
        pk, first = pk[new], first[new]
    for part, col in zip(parts, (xyz, rgb, cls)):
        part.append(col[first])
    keys = np.concatenate([keys, pk])
    keys.sort(kind="stable")  # timsort: merges the two sorted runs in O(N)
    return keys


def _stream(f, voxel: float, chunk_bytes: int):
    """Parse blocks, keep the first point per voxel; returns (xyz, rgb, cls, points_read, points_declared)."""
    keys = np.empty(0, np.int64)
    parts: tuple[list, list, list] = ([], [], [])
    pending: list[tuple[np.ndarray, ...]] = []
    pending_rows = bytes_read = points_read = 0
    next_report = REPORT_EVERY
    head = b""  # until the header and count lines are complete
    declared = None

    for block in read_blocks(f, chunk_bytes):
        bytes_read += len(block)
        if declared is None:
            head += block
            if head.count(b"\n") < 2:
                continue
            header, count, block = head.split(b"\n", 2)
            if not header.startswith(b"//"):
                raise ValueError(f"line 1 is not a '//' header: {header[:60]!r}")
            try:
                declared = int(count)
            except ValueError:
                raise ValueError(f"line 2 is not an integer point count: {count[:60]!r}") from None
            head = b""
        if not block.strip():
            continue
        data = np.loadtxt(io.BytesIO(block), ndmin=2)
        if data.shape[1] != 8:
            raise ValueError(f"expected 8 columns, got {data.shape[1]}")
        points_read += len(data)
        bkeys, first = np.unique(voxel_keys(data[:, :3], voxel), return_index=True)
        data = data[first]
        pending.append(
            (bkeys, data[:, :3].astype(np.float32), data[:, 3:6].astype(np.uint8), np.rint(data[:, 7]).astype(np.uint8))
        )
        pending_rows += len(bkeys)
        if pending_rows >= MIN_PENDING:
            keys = _consolidate(keys, parts, pending)
            pending, pending_rows = [], 0
        if bytes_read >= next_report:
            next_report += REPORT_EVERY
            print(
                f"  {bytes_read / 1e9:.1f} GB read, {points_read} points, <= {len(keys) + pending_rows} voxels",
                flush=True,
            )

    if declared is None:
        raise ValueError("member ended before the header and count lines")
    if pending:
        keys = _consolidate(keys, parts, pending)
    del keys, pending  # free before the final concatenations
    if not parts[0]:
        raise ValueError("member has no points")
    out = []
    for part in parts:  # one array at a time
        out.append(np.concatenate(part))
        part.clear()
    return (*out, points_read, declared)

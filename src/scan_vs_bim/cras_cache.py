"""Stream the CRAS annotated scan (one huge ASCII zip member) into a small voxel-subsampled cache.

The member is never extracted or loaded whole: it is read in fixed-size byte blocks through
`zipfile`, parsed per block, and reduced to the first point (stream order) per voxel. Memory is
about 24 bytes per occupied voxel plus one block, not a function of the input point count.
The cache keeps xyz (float32, ~um precision for the lab's local metre coordinates), rgb (uint8)
and class (uint8); intensity is dropped.
"""

import io
import json
import logging
import zipfile
from pathlib import Path
from typing import IO, Iterator, NamedTuple

import numpy as np

log = logging.getLogger(__name__)

MIN_PENDING_ROWS: int = 2_000_000  # rows of deduped blocks buffered before the next consolidation
VOXEL_AXIS_BITS: int = 21  # per voxel axis index; 2**21 cells (21 km at 1 cm)
VOXEL_AXIS_OFFSET: int = 1 << (VOXEL_AXIS_BITS - 1)
REPORT_EVERY_BYTES: int = 1 << 30


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
    idx = np.floor(xyz / voxel).astype(np.int64) + VOXEL_AXIS_OFFSET
    if idx.min() < 0 or idx.max() >= 1 << VOXEL_AXIS_BITS:
        raise ValueError(f"voxel index out of range for voxel size {voxel}")
    return (idx[:, 0] << (2 * VOXEL_AXIS_BITS)) | (idx[:, 1] << VOXEL_AXIS_BITS) | idx[:, 2]


def _read_meta(path: Path) -> dict | None:
    try:
        with np.load(path) as d:
            return json.loads(str(d["meta"]))
    except (OSError, KeyError, ValueError):
        return None


def build_cache(zip_path: str | Path, cache_path: str | Path, voxel: float = 0.01, chunk_bytes: int = 64 << 20) -> dict:
    """Voxel-subsample the single member of `zip_path` into an `.npz` at `cache_path`."""
    cache_path = Path(cache_path)
    with zipfile.ZipFile(zip_path) as z:
        members = [i for i in z.infolist() if not i.is_dir()]
        if len(members) != 1:
            raise ValueError(f"expected one member in {zip_path}, found {len(members)}")
        info = members[0]

        old = _read_meta(cache_path) if cache_path.exists() else None
        if old and (old["voxel_size"], old["member"], old["member_size"]) == (voxel, info.filename, info.file_size):
            log.info("skip %s (up to date)", cache_path)
            return old

        with z.open(info) as f:
            streamed = _stream(f, voxel, chunk_bytes)

    xyz, rgb, cls, points_read, points_declared = streamed
    if points_read != points_declared:
        raise ValueError(f"read {points_read} points but the header declares {points_declared}; truncated or corrupt")
    meta = {
        "voxel_size": voxel,
        "member": info.filename,
        "member_size": info.file_size,
        "points_read": points_read,
        "points_declared": points_declared,
        "points_kept": len(xyz),
        "extent_min": xyz.min(axis=0).tolist(),
        "extent_max": xyz.max(axis=0).tolist(),
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_path.with_name(cache_path.name + ".tmp")
    with open(tmp, "wb") as out:
        np.savez(out, xyz=xyz, rgb=rgb, cls=cls, meta=json.dumps(meta))
    tmp.replace(cache_path)
    log.info("ok   %s (%d points)", cache_path, len(xyz))
    return meta


class _Streamed(NamedTuple):
    xyz: np.ndarray
    rgb: np.ndarray
    cls: np.ndarray
    points_read: int
    points_declared: int


class _KeptVoxels:
    """Voxels kept so far: sorted unique `keys` and, per column, append-only data segments."""

    def __init__(self) -> None:
        self.keys: np.ndarray = np.empty(0, np.int64)
        self.parts: tuple[list[np.ndarray], list[np.ndarray], list[np.ndarray]] = ([], [], [])

    def __len__(self) -> int:
        return len(self.keys)

    def fold(self, pending: list[tuple[np.ndarray, ...]]) -> None:
        """Fold pending (keys, xyz, rgb, cls) blocks in. Earlier rows win; only rows whose voxel is new
        are appended, as one segment, never re-copied."""
        pk, xyz, rgb, cls = (np.concatenate(c) for c in zip(*pending))
        pk, first = np.unique(pk, return_index=True)  # stable: earlier rows win
        if len(self.keys):
            pos = np.minimum(np.searchsorted(self.keys, pk), len(self.keys) - 1)
            new = self.keys[pos] != pk
            pk, first = pk[new], first[new]
        for part, col in zip(self.parts, (xyz, rgb, cls)):
            part.append(col[first])
        self.keys = np.concatenate([self.keys, pk])
        self.keys.sort(kind="stable")  # timsort: merges the two sorted runs in O(N)

    def drain(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """The (xyz, rgb, cls) columns, one array at a time, freeing each column's segments. Single use."""
        del self.keys
        if not self.parts[0]:
            raise ValueError("member has no points")
        out: list[np.ndarray] = []
        for part in self.parts:
            out.append(np.concatenate(part))
            part.clear()
        return out[0], out[1], out[2]


def _stream(f: IO[bytes], voxel: float, chunk_bytes: int) -> _Streamed:
    """Parse blocks, keep the first point per voxel."""
    kept = _KeptVoxels()
    pending: list[tuple[np.ndarray, ...]] = []
    pending_rows = bytes_read = points_read = 0
    next_report = REPORT_EVERY_BYTES
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
        if pending_rows >= MIN_PENDING_ROWS:
            kept.fold(pending)
            pending, pending_rows = [], 0
        if bytes_read >= next_report:
            next_report += REPORT_EVERY_BYTES
            log.info("  %.1f GB read, %d points, <= %d voxels", bytes_read / 1e9, points_read, len(kept) + pending_rows)

    if declared is None:
        raise ValueError("member ended before the header and count lines")
    if pending:
        kept.fold(pending)
    del pending  # free before the final concatenations
    return _Streamed(*kept.drain(), points_read, declared)

"""PC2Model data prep: find samples by their transform file without downloading the 10 GB zip."""

import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from scan_vs_bim.fetch import ReadRange, data_start

URL = "https://zenodo.org/api/records/17581812/files/PC2Model_v1.4.zip/content"


@dataclass(frozen=True)
class Sample:
    folder: str  # zip path of the sample folder, no trailing slash
    compressed_size: int  # total compressed bytes of all members
    transform: zipfile.ZipInfo


def parse_transform(text: str) -> np.ndarray:
    rows = [line.split() for line in text.strip().splitlines()]
    T = np.array(rows, dtype=np.float64)
    if T.shape != (4, 4):
        raise ValueError(f"transform must be 4x4, got {T.shape}")
    return T


def scale_of(T: np.ndarray) -> float:
    """Uniform scale s of the 3x3 block s*R: cube root of its determinant (rotation-invariant)."""
    return float(np.cbrt(abs(np.linalg.det(T[:3, :3]))))


def group_samples(infos: list[zipfile.ZipInfo]) -> list[Sample]:
    """Group members by parent folder; samples without a transform file are dropped."""
    sizes: dict[str, int] = {}
    transforms: dict[str, zipfile.ZipInfo] = {}
    for i in infos:
        if i.is_dir():
            continue
        folder, _, name = i.filename.rpartition("/")
        sizes[folder] = sizes.get(folder, 0) + i.compress_size
        if name.startswith("transformation_matrix"):
            transforms[folder] = i
    return [Sample(f, sizes[f], t) for f, t in transforms.items()]


def read_member(read_range: ReadRange, info: zipfile.ZipInfo) -> bytes:
    """Read one small member into memory via ranged reads; verifies size and CRC32."""
    start = data_start(read_range, info)
    raw = read_range(start, start + info.compress_size - 1)
    data = zlib.decompress(raw, -15) if info.compress_type == zipfile.ZIP_DEFLATED else raw
    if zlib.crc32(data) != info.CRC or len(data) != info.file_size:
        raise ValueError(f"CRC/size mismatch for {info.filename}")
    return data


def pick_smallest_scaled(samples: list[Sample], scales: dict[str, float], tol: float = 1e-3) -> Sample:
    """Smallest sample (by compressed bytes) with |scale - 1| > tol."""
    scaled = [s for s in samples if abs(scales[s.folder] - 1) > tol]
    if not scaled:
        raise ValueError("no scaled sample found")
    return min(scaled, key=lambda s: s.compressed_size)


def pick_gate_samples(
    samples: list[Sample], scales: dict[str, float], categories: list[str], tol: float = 1e-3
) -> list[Sample]:
    """Per category: the smallest scaled sample, the smallest unscaled one, then the next smallest remaining.

    Size ties break by folder name, so the result does not depend on input order.
    """
    picked = []
    for category in categories:
        mine = sorted((s for s in samples if s.folder.split("/")[1] == category), key=lambda s: (s.compressed_size, s.folder))
        if len(mine) < 3:
            raise ValueError(f"category {category!r} has fewer than 3 samples")
        scaled = next((s for s in mine if abs(scales[s.folder] - 1) > tol), None)
        unscaled = next((s for s in mine if abs(scales[s.folder] - 1) <= tol), None)
        if scaled is None:
            raise ValueError(f"category {category!r} has no scaled sample")
        if unscaled is None:
            raise ValueError(f"category {category!r} has no unscaled sample")
        rest = next(s for s in mine if s not in (scaled, unscaled))
        picked += [scaled, unscaled, rest]
    return picked


def cached_scales(read_range: ReadRange, samples: list[Sample], cache: Path) -> dict[str, float]:
    """Scale of every sample's ground-truth transform; transform texts are cached in `cache`, missing ones fetched."""
    cache.mkdir(parents=True, exist_ok=True)
    scales = {}
    for n, s in enumerate(samples, 1):
        f = cache / (s.folder.replace("/", "__") + ".txt")
        if not f.exists():
            f.write_bytes(read_member(read_range, s.transform))
            print(f"[{n}/{len(samples)}] {s.folder}", flush=True)
        scales[s.folder] = scale_of(parse_transform(f.read_text()))
    return scales

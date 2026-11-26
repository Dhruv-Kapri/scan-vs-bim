"""PC2Model data prep: find samples by their transform file without downloading the 10 GB zip."""

import logging
import zipfile
import zlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import open3d as o3d

from scan_vs_bim.fetch import ReadRange, data_start, extract_zip_member
from scan_vs_bim.load import load_e57, seed_all
from scan_vs_bim.obj_mesh import load_model_mesh

log = logging.getLogger(__name__)

URL = "https://zenodo.org/api/records/17581812/files/PC2Model_v1.4.zip/content"

BUILDING_CATEGORIES: tuple[str, ...] = ("house", "indoor_modelling", "ISPRS_indoor_modeling_benchmark")


@dataclass(frozen=True)
class Sample:
    folder: str  # zip path of the sample folder, no trailing slash
    compressed_size: int  # total compressed bytes of all members
    transform: zipfile.ZipInfo

    @property
    def category(self) -> str:
        """The zip folder segment: PC2Model_v1.4/<category>/<sample>."""
        return self.folder.split("/")[1]


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
        mine = sorted((s for s in samples if s.category == category), key=lambda s: (s.compressed_size, s.folder))
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
            log.info("[%d/%d] %s", n, len(samples), s.folder)
        scales[s.folder] = scale_of(parse_transform(f.read_text()))
    return scales


def download_order(rows: Iterable[Mapping[str, str]]) -> list[str]:
    """Sample folders from pc2model_scales.csv rows: building categories first, then the rest, each in input order."""
    rows = list(rows)
    buildings = [r["sample"] for r in rows if r["category"] in BUILDING_CATEGORIES]
    others = [r["sample"] for r in rows if r["category"] not in BUILDING_CATEGORIES]
    return buildings + others


def fetch_samples(read_range: ReadRange, infos: Sequence[zipfile.ZipInfo], folders: Sequence[str], data_dir: Path) -> None:
    """Extract every member of each sample folder into data_dir/<folder basename>/; complete files are skipped."""
    for n, folder in enumerate(folders, 1):
        members = [i for i in infos if i.filename.startswith(folder + "/") and not i.is_dir()]
        if not members:
            raise ValueError(f"no members under {folder!r} in the zip")
        for info in members:
            extract_zip_member(read_range, info, data_dir / Path(folder).name / Path(info.filename).name)
        log.info("done %d/%d: %s", n, len(folders), folder)


class EmptyModelError(ValueError):
    """A sample's model OBJ has no triangles at all. Carries the ground truth, which the benchmark still reports (#53)."""

    def __init__(self, obj: Path, T_gt: np.ndarray) -> None:
        super().__init__(f"{obj} has no triangles")
        self.T_gt: np.ndarray = T_gt


@dataclass(frozen=True)
class LoadedSample:
    """One PC2Model sample as 05a, 05c, 02 and the benchmark load it (#33)."""

    mesh: o3d.geometry.TriangleMesh   # the model, non-triangle faces cut (`load_model_mesh`)
    T_gt: np.ndarray   # ground truth: maps the scan onto the model
    model: o3d.geometry.PointCloud   # `model_points` uniform samples of the mesh surface
    scan: o3d.geometry.PointCloud   # at most `max_scan_points`, seeded subsample
    diag: float   # diagonal of the mesh's bounding box


def load_sample(d: Path, model_points: int, max_scan_points: int, seed: int, chunk_points: int = 1_000_000) -> LoadedSample:
    """Load the sample in folder `d` (model_*.obj, transformation_matrix_*.txt, pointcloud_*_transformed.e57).

    The call order is part of the numbers: parse the model, seed numpy and Open3D with `seed`, sample the surface, then load the scan with the same seed.
    Raises FileNotFoundError naming the missing pattern, and EmptyModelError (before any seeding or sampling, the scan unread) for a model without triangles.
    """
    files: list[Path] = []
    for g in ("model_*.obj", "transformation_matrix_*.txt", "pointcloud_*_transformed.e57"):
        found = next(d.glob(g), None)
        if found is None:
            raise FileNotFoundError(f"{d}/{g} is missing")
        files.append(found)
    obj, txt, e57 = files
    mesh = load_model_mesh(obj)
    T_gt = parse_transform(txt.read_text())
    if not mesh.has_triangles():
        raise EmptyModelError(obj, T_gt)
    seed_all(seed)
    model = mesh.sample_points_uniformly(model_points)
    scan = load_e57(e57, max_scan_points, seed, chunk_points)
    return LoadedSample(mesh, T_gt, model, scan, float(np.linalg.norm(mesh.get_axis_aligned_bounding_box().get_extent())))

"""PC2Model data prep: find samples by their transform file without downloading the 10 GB zip."""

import logging
import tempfile
import zipfile
import zlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import open3d as o3d

from scan_vs_bim.fetch import ReadRange, data_start, extract_zip_member

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


def _newell_normal(points: np.ndarray) -> np.ndarray:
    """Normal of a (planar) polygon, length = twice its area; points the way the polygon winds (counter-clockwise seen from its tip)."""
    return np.cross(points, np.roll(points, -1, axis=0)).sum(axis=0)


def _is_convex(points: np.ndarray, normal: np.ndarray) -> bool:
    """Every consecutive turn bends the way the polygon winds (no reflex vertex); collinear points pass, within a tolerance relative to its size."""
    edges = np.roll(points, -1, axis=0) - points
    turns = np.cross(np.roll(edges, 1, axis=0), edges) @ (normal / np.linalg.norm(normal))
    return bool(np.all(turns >= -1e-6 * np.ptp(points, axis=0).max() ** 2))


def _fan(n: int) -> list[tuple[int, int, int]]:
    """Triangles (0, i, i + 1) of an n-gon, as vertex positions in the polygon."""
    return [(0, i, i + 1) for i in range(1, n - 1)]


def _ear_clip(points: np.ndarray, normal: np.ndarray) -> list[tuple[int, int, int]]:
    """Triangles of a simple planar polygon by ear clipping in 2D: repeatedly cut off a convex vertex whose triangle holds no other vertex.
    Triangles keep the polygon's winding. With no ear left (a degenerate or self-intersecting polygon) the remaining polygon is fanned."""
    n_hat = normal / np.linalg.norm(normal)
    u = np.cross(n_hat, np.eye(3)[np.argmin(np.abs(n_hat))])
    u /= np.linalg.norm(u)
    xy = np.column_stack((points @ u, points @ np.cross(n_hat, u)))  # (u, v, n_hat) is right-handed: the polygon runs counter-clockwise in xy
    tol = 1e-12 * np.ptp(points, axis=0).max() ** 2

    def cross(a: int, b: int, c: int) -> float:
        (bx, by), (cx, cy) = xy[b] - xy[a], xy[c] - xy[a]
        return float(bx * cy - by * cx)

    def is_ear(a: int, b: int, c: int, others: list[int]) -> bool:
        if cross(a, b, c) <= tol:
            return False
        return not any(
            cross(a, b, q) >= -tol and cross(b, c, q) >= -tol and cross(c, a, q) >= -tol
            for q in others
            if not any(np.array_equal(xy[q], xy[t]) for t in (a, b, c))
        )

    remaining = list(range(len(points)))
    triangles: list[tuple[int, int, int]] = []
    while len(remaining) > 3:
        for k, b in enumerate(remaining):
            a, c = remaining[k - 1], remaining[(k + 1) % len(remaining)]
            if is_ear(a, b, c, remaining):
                triangles.append((a, b, c))
                del remaining[k]
                break
        else:
            return triangles + [(remaining[0], remaining[i], remaining[i + 1]) for i in range(1, len(remaining) - 1)]
    return triangles + [(remaining[0], remaining[1], remaining[2])]


def _triangulate(points: np.ndarray) -> list[tuple[int, int, int]]:
    """Fan for a convex polygon (or one with no area), ear clipping for a concave one: a fan over a concave face adds surface outside it (#53)."""
    normal = _newell_normal(points)
    if np.linalg.norm(normal) == 0 or _is_convex(points, normal):
        return _fan(len(points))
    return _ear_clip(points, normal)


def _vertex_index(token: str, seen: int) -> int:
    """0-based vertex index of an OBJ face token (`v`, `v/vt`, `v//vn`, `v/vt/vn`; 1-based, negative = relative to the `seen` vertices read so far)."""
    index = int(token.split("/")[0])
    return index - 1 if index > 0 else seen + index


def load_model_mesh(obj: Path) -> o3d.geometry.TriangleMesh:
    """Read a model OBJ with every quad and n-gon cut into triangles: Open3D's reader (ASSIMP) silently drops non-triangle faces (#53).
    A convex face is fanned from its first vertex; a concave one is ear-clipped, since a fan over it adds surface outside the face.
    A model of triangles only is read from the original file, unchanged."""
    lines = obj.read_text().splitlines(keepends=True)
    out: list[str] = []
    vertices: list[list[float]] = []
    changed = False
    for line in lines:
        tokens = line.split()
        if len(tokens) > 3 and tokens[0] == "v":
            vertices.append([float(t) for t in tokens[1:4]])
        if len(tokens) > 4 and tokens[0] == "f":
            corners = tokens[1:]
            points = np.array([vertices[_vertex_index(t, len(vertices))] for t in corners])
            out += [f"f {corners[a]} {corners[b]} {corners[c]}\n" for a, b, c in _triangulate(points)]
            changed = True
        else:
            out.append(line)
    if not changed:
        return o3d.io.read_triangle_mesh(obj)
    # beside the original, so a relative `mtllib` still resolves; the name does not match model_*.obj
    with tempfile.NamedTemporaryFile("w", dir=obj.parent, prefix=".triangulated_", suffix=".obj", delete=False) as tmp:
        tmp.writelines(out)
    try:
        return o3d.io.read_triangle_mesh(Path(tmp.name))
    finally:
        Path(tmp.name).unlink()

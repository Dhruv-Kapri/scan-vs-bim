"""PC2Model data prep: find samples by their transform file without downloading the 10 GB zip."""

import logging
import tempfile
import zipfile
import zlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import mapbox_earcut
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


def _signed_area(xy: np.ndarray) -> float:
    """Shoelace area of a 2D ring: positive counter-clockwise."""
    return 0.5 * float(np.dot(xy[:, 0], np.roll(xy[:, 1], -1)) - np.dot(np.roll(xy[:, 0], -1), xy[:, 1]))


def _contains(ring: np.ndarray, point: np.ndarray) -> bool:
    """Even-odd test of a 2D point against a 2D ring."""
    x, y = point
    nxt = np.roll(ring, -1, axis=0)
    crossing = (ring[:, 1] > y) != (nxt[:, 1] > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        x_at = ring[:, 0] + (y - ring[:, 1]) * (nxt[:, 0] - ring[:, 0]) / (nxt[:, 1] - ring[:, 1])
    return bool(np.count_nonzero(crossing & (x < x_at)) % 2)


def _rings(points: np.ndarray) -> list[list[int]]:
    """Corner indices of the simple rings a face splits into at repeated vertex positions (exact equality): walk the corners on a stack,
    and when a position already on the stack recurs, the corners since it close a ring. A keyhole face (a hole joined to the outline by a bridge
    walked twice) or a pinched one becomes its outline and its holes. Rings with fewer than 3 corners are dropped."""
    keys = [tuple(p) for p in points]
    stack: list[int] = []
    rings: list[list[int]] = []
    for i, key in enumerate(keys):
        seen = next((k for k, j in enumerate(stack) if keys[j] == key), None)
        if seen is not None:
            rings.append(stack[seen:])
            del stack[seen:]
        stack.append(i)
    rings.append(stack)
    return [r for r in rings if len(r) >= 3]


def _earcut(points: np.ndarray, normal: np.ndarray) -> list[tuple[int, int, int]]:
    """Triangles of a concave face as corner indices, keeping its winding: the face is split at repeated vertices into rings (counter-clockwise
    in its Newell plane = outlines, clockwise = holes), each hole goes to the smallest outline containing its vertex mean (a hole inside no outline
    is triangulated alone), and each outline with its holes is triangulated by earcut. Earcut returns counter-clockwise triangles whatever the
    input winding, which is the face's winding in the plane (u, v, n) used here. Empty if earcut finds no triangle."""
    n_hat = normal / np.linalg.norm(normal)
    u = np.cross(n_hat, np.eye(3)[np.argmin(np.abs(n_hat))])
    u /= np.linalg.norm(u)
    xy = np.column_stack((points @ u, points @ np.cross(n_hat, u)))  # (u, v, n_hat) is right-handed: the face runs counter-clockwise in xy
    areas = {tuple(r): _signed_area(xy[r]) for r in _rings(points)}
    outlines = [r for r, a in areas.items() if a > 0]
    holes: dict[tuple[int, ...], list[tuple[int, ...]]] = {r: [] for r in outlines}
    groups: list[list[tuple[int, ...]]] = []
    for hole in (r for r, a in areas.items() if a < 0):
        inside = [o for o in outlines if _contains(xy[list(o)], xy[list(hole)].mean(axis=0))]
        if inside:
            holes[min(inside, key=areas.__getitem__)].append(hole)
        else:
            groups.append([hole])
    groups += [[o, *holes[o]] for o in outlines]
    triangles: list[tuple[int, int, int]] = []
    for group in groups:
        corners = [i for ring in group for i in ring]
        ends = np.cumsum([len(ring) for ring in group]).astype(np.uint32)
        found = mapbox_earcut.triangulate_float64(xy[corners], ends).reshape(-1, 3)
        triangles += [(corners[a], corners[b], corners[c]) for a, b, c in found]
    return triangles


def _triangulate(points: np.ndarray) -> list[tuple[int, int, int]]:
    """Fan for a convex polygon (or one with no area); for a concave one, rings (outline + holes) split off at repeated vertices and triangulated
    with earcut, because a fan or a plain ear clip leaves the face, or overlaps, on these faces (#53). A face earcut gives no triangle for is fanned."""
    normal = _newell_normal(points)
    if np.linalg.norm(normal) == 0 or _is_convex(points, normal):
        return _fan(len(points))
    return _earcut(points, normal) or _fan(len(points))


def _vertex_index(token: str, seen: int) -> int:
    """0-based vertex index of an OBJ face token (`v`, `v/vt`, `v//vn`, `v/vt/vn`; 1-based, negative = relative to the `seen` vertices read so far)."""
    index = int(token.split("/")[0])
    return index - 1 if index > 0 else seen + index


def load_model_mesh(obj: Path) -> o3d.geometry.TriangleMesh:
    """Read a model OBJ with every quad and n-gon cut into triangles: Open3D's reader (ASSIMP) silently drops non-triangle faces (#53).
    A convex face is fanned from its first vertex; a concave one is split at repeated vertices into rings (outline + holes) and triangulated with
    earcut, since a fan over it adds surface outside the face and a plain ear clip overlaps on faces that touch themselves.
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

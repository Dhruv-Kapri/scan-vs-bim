"""Check #53's loader on every PC2Model model with non-triangle faces, face by face, so a lost face of any size shows.

Each n-gon's triangles (`pc2model._triangulate`, what `load_model_mesh` writes) are measured against the face's own outline, computed
independently in the face's Newell plane: a simple outline by its Newell polygon area; one that is not simple (it touches itself at a
repeated corner, or its edges cross) as the area it covers: its edges cut the plane into cells (shapely) and each cell with a nonzero
winding number counts, so a hole inside it (winding 0) is left out and a flap wound backwards (winding -1) counts, where the Newell area
would subtract it. Any surface spanning an outline covers at least its projection, so:

- short: faces whose triangles cover less than their outline (by more than REL_TOL): a lost or partly lost face. Must be 0.
- mesh_vs_faces: the loaded mesh's area against the sum of all faces' triangles (OBJ triangles by cross product): nothing dropped or added
  by Open3D's reader. Must be within REL_TOL.
- flat_excess: on flat faces (every corner within FLAT_FRACTION of its extent of the plane), where triangles and outline should agree
  exactly, the area by which the triangles exceed the outline, relative to the model's area (overlapping triangles). Must be within REL_TOL.
  On faces that are not flat the triangles exceed the projected outline by the tilt, so no excess is checked there.

A face with zero Newell area has no plane; it is counted and printed, not checked. Prints one line per model."""

import argparse
from pathlib import Path

import numpy as np
import open3d as o3d
from shapely import LinearRing, MultiLineString, get_parts, polygonize, unary_union

from scan_vs_bim.benchmark import non_triangle_share
from scan_vs_bim.pc2model import _triangulate, load_model_mesh

REPO = Path(__file__).resolve().parent.parent
REL_TOL: float = 1e-6        # relative tolerance of every check
FLAT_FRACTION: float = 1e-6  # a face is flat when no corner lies further than this fraction of its extent off its plane


def winding_number(xy: np.ndarray, x: float, y: float) -> int:
    """Winding number of the closed 2D polyline `xy` around the point (x, y)."""
    winding = 0
    for (x0, y0), (x1, y1) in zip(xy, np.roll(xy, -1, axis=0)):
        side = (x1 - x0) * (y - y0) - (x - x0) * (y1 - y0)
        if y0 <= y < y1 and side > 0:
            winding += 1
        elif y1 <= y < y0 and side < 0:
            winding -= 1
    return winding


def in_plane(pts: np.ndarray, normal: np.ndarray) -> np.ndarray:
    """A polygon's corners in 2D coordinates of the plane perpendicular to `normal`."""
    n_hat = normal / np.linalg.norm(normal)
    axis_u = np.cross(np.eye(3)[np.argmin(np.abs(n_hat))], n_hat)
    axis_u /= np.linalg.norm(axis_u)
    return np.column_stack((pts @ axis_u, pts @ np.cross(n_hat, axis_u)))


def covered_area(xy: np.ndarray) -> float:
    """Area of the region a 2D polygon covers: the cells its edges cut the plane into with a nonzero winding number."""
    edges = MultiLineString([[xy[i], xy[(i + 1) % len(xy)]] for i in range(len(xy))])
    cells = get_parts(polygonize(get_parts(unary_union(edges))))
    return float(sum(c.area for c in cells if winding_number(xy, *c.representative_point().coords[0])))


def triangles_area(pts: np.ndarray, triangles: list[tuple[int, int, int]]) -> float:
    """Summed area of triangles given as corner indices into `pts`."""
    return float(sum(0.5 * np.linalg.norm(np.cross(pts[b] - pts[a], pts[c] - pts[a])) for a, b, c in triangles))


def face_area(pts: np.ndarray, normal: np.ndarray) -> float:
    """A planar n-gon's area, or a non-planar one's projected area: Newell's if it is simple in its plane, else the area it covers."""
    xy = in_plane(pts, normal)
    return covered_area(xy) if not LinearRing(xy).is_simple else 0.5 * float(np.linalg.norm(normal))


def check_obj(obj: Path) -> dict[str, float]:
    """Per-face check of one OBJ: the sum of its faces' triangles, the faces short of their outline, the flat faces' excess, the degenerate faces."""
    vertices: list[list[float]] = []
    total = flat_excess = 0.0
    short = degenerate = 0
    with obj.open(errors="replace") as f:
        for line in f:
            tokens = line.split()
            if len(tokens) > 3 and tokens[0] == "v":
                vertices.append([float(t) for t in tokens[1:4]])
            elif len(tokens) > 3 and tokens[0] == "f":
                idx = [int(t.split("/")[0]) for t in tokens[1:]]
                pts = np.array([vertices[i - 1] if i > 0 else vertices[len(vertices) + i] for i in idx])
                if len(pts) == 3:
                    total += triangles_area(pts, [(0, 1, 2)])
                    continue
                triangles, extra = _triangulate(pts)
                got = triangles_area(np.vstack((pts, extra)), triangles)
                total += got
                normal = np.cross(pts, np.roll(pts, -1, axis=0)).sum(axis=0)
                if not np.linalg.norm(normal):
                    degenerate += 1
                    continue
                want = face_area(pts, normal)
                short += got < want * (1 - REL_TOL)
                off_plane = np.abs((pts - pts.mean(axis=0)) @ (normal / np.linalg.norm(normal))).max()
                if off_plane <= FLAT_FRACTION * np.ptp(pts, axis=0).max():
                    flat_excess += max(got - want, 0.0)
    return dict(faces_area=total, short=short, flat_excess=flat_excess, degenerate=degenerate)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=REPO / "data" / "pc2model")
    args = ap.parse_args(argv)
    o3d.utility.set_verbosity_level(o3d.utility.VerbosityLevel.Error)
    off = 0
    for obj in sorted(args.data.glob("*/model_*.obj")):
        if non_triangle_share(obj) == 0:
            continue
        r = check_obj(obj)
        loaded = load_model_mesh(obj).get_surface_area()
        mesh_gap = (loaded - r["faces_area"]) / r["faces_area"]
        flat_excess = r["flat_excess"] / r["faces_area"]
        ok = r["short"] == 0 and abs(mesh_gap) <= REL_TOL and flat_excess <= REL_TOL
        off += not ok
        print(f"{obj.parent.name}\tloaded={loaded:.6g}\tshort={r['short']:.0f}\tmesh_vs_faces={mesh_gap:.1e}\tflat_excess={flat_excess:.1e}"
              f" ({r['flat_excess']:.2g} m2)\tdegenerate={r['degenerate']:.0f}\t{'ok' if ok else 'OFF'}", flush=True)
    print(f"models off: {off}")


if __name__ == "__main__":
    main()

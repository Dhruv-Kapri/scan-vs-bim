"""Check #53's loader on every PC2Model model with non-triangle faces: the area `load_model_mesh` loads against the OBJ's own area,
computed independently (triangles by cross product, simple n-gons by their Newell polygon area). An n-gon that touches itself (a repeated
corner position) is measured as the area it covers: its outline is cut into cells (shapely) and each cell with a nonzero winding number counts,
so a hole inside it (winding 0) is left out and a flap wound backwards (winding -1) counts, where the Newell area would subtract it.
Non-planar n-gons (more than 1% of their size off their plane) have no single area; their summed area is printed and a gap up to it is
accepted. Prints one line per model."""

import argparse
from pathlib import Path

import numpy as np
import open3d as o3d
from shapely import MultiLineString, get_parts, polygonize, unary_union

from scan_vs_bim.benchmark import non_triangle_share
from scan_vs_bim.pc2model import load_model_mesh

REPO = Path(__file__).resolve().parent.parent
REL_TOL: float = 1e-6        # loaded vs OBJ area, relative, for a model whose n-gons are all planar
PLANAR_FRACTION: float = 0.01  # an n-gon is non-planar when a corner lies further than this fraction of its extent off its plane


def winding_number(xy: np.ndarray, point: np.ndarray) -> int:
    """Winding number of the closed 2D polyline `xy` around `point`."""
    x, y = point
    w = 0
    for (x0, y0), (x1, y1) in zip(xy, np.roll(xy, -1, axis=0)):
        side = (x1 - x0) * (y - y0) - (x - x0) * (y1 - y0)
        if y0 <= y < y1 and side > 0:
            w += 1
        elif y1 <= y < y0 and side < 0:
            w -= 1
    return w


def covered_area(pts: np.ndarray, normal: np.ndarray) -> float:
    """Area of the plane region a (planar) polygon covers: the cells its edges cut the plane into with a nonzero winding number."""
    n_hat = normal / np.linalg.norm(normal)
    u = np.cross(np.eye(3)[np.argmin(np.abs(n_hat))], n_hat)
    u /= np.linalg.norm(u)
    xy = np.column_stack((pts @ u, pts @ np.cross(n_hat, u)))
    edges = MultiLineString([[xy[i], xy[(i + 1) % len(xy)]] for i in range(len(xy))])
    cells = get_parts(polygonize(get_parts(unary_union(edges))))
    return float(sum(c.area for c in cells if winding_number(xy, np.array(c.representative_point().coords[0]))))


def obj_area(obj: Path) -> tuple[float, float]:
    """(area of all faces, area of the non-planar n-gons among them), from the OBJ's `v` and `f` lines."""
    vertices: list[list[float]] = []
    area = nonplanar = 0.0
    with obj.open(errors="replace") as f:
        for line in f:
            tokens = line.split()
            if len(tokens) > 3 and tokens[0] == "v":
                vertices.append([float(t) for t in tokens[1:4]])
            elif len(tokens) > 3 and tokens[0] == "f":
                idx = [int(t.split("/")[0]) for t in tokens[1:]]
                pts = np.array([vertices[i - 1] if i > 0 else vertices[len(vertices) + i] for i in idx])
                normal = np.cross(pts, np.roll(pts, -1, axis=0)).sum(axis=0)
                a = 0.5 * float(np.linalg.norm(normal))
                if a > 0 and len({tuple(p) for p in pts}) < len(pts):
                    a = covered_area(pts, normal)
                area += a
                if len(pts) > 3 and a > 0:
                    off = np.abs((pts - pts.mean(axis=0)) @ (normal / np.linalg.norm(normal))).max()
                    nonplanar += a if off > PLANAR_FRACTION * np.ptp(pts, axis=0).max() else 0.0
    return area, nonplanar


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=REPO / "data" / "pc2model")
    args = ap.parse_args(argv)
    o3d.utility.set_verbosity_level(o3d.utility.VerbosityLevel.Error)
    off = 0
    for obj in sorted(args.data.glob("*/model_*.obj")):
        if non_triangle_share(obj) == 0:
            continue
        want, nonplanar = obj_area(obj)
        got = load_model_mesh(obj).get_surface_area()
        ok = abs(got - want) <= REL_TOL * want or abs(got - want) <= nonplanar
        off += not ok
        print(f"{obj.parent.name}\tobj_area={want:.6g}\tloaded={got:.6g}\trel_gap={(got - want) / want:.2e}\t"
              f"nonplanar_area={nonplanar:.3g}\t{'ok' if ok else 'OFF'}", flush=True)
    print(f"models off: {off}")


if __name__ == "__main__":
    main()

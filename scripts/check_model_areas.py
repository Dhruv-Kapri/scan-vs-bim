"""Check #53's loader on every PC2Model model with non-triangle faces: the area `load_model_mesh` loads against the OBJ's own area,
computed independently (triangles by cross product, n-gons by their Newell polygon area). Non-planar n-gons (more than 1% of their size
off their plane) have no single area; their summed area is printed and a gap up to it is accepted. Prints one line per model."""

import argparse
from pathlib import Path

import numpy as np
import open3d as o3d

from scan_vs_bim.benchmark import non_triangle_share
from scan_vs_bim.pc2model import load_model_mesh

REPO = Path(__file__).resolve().parent.parent
REL_TOL: float = 1e-6        # loaded vs OBJ area, relative, for a model whose n-gons are all planar
PLANAR_FRACTION: float = 0.01  # an n-gon is non-planar when a corner lies further than this fraction of its extent off its plane


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

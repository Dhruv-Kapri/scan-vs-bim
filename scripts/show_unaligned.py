"""Stage 0: load an E57 scan and an IFC model and show them in one Open3D window, unaligned."""

import argparse
import os
import resource
import time
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import numpy as np
import open3d as o3d
import pye57

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_E57 = (
    ROOT / "data/pc2model/real-indoor_modelling_3-ISPRS_indoor_modelling-UVigo"
    / "pointcloud_real-indoor_modelling_3-ISPRS_indoor_modelling-UVigo_transformed.e57"
)
DEFAULT_IFC = ROOT / "data/cras/craslabbim.ifc"


def peak_rss_gb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9  # bytes on macOS


def bbox_str(pts: np.ndarray) -> str:
    lo, hi = pts.min(0), pts.max(0)
    return f"min {np.round(lo, 2)} max {np.round(hi, 2)} size {np.round(hi - lo, 2)}"


def load_e57(path: Path, max_points: int, seed: int = 0) -> o3d.geometry.PointCloud:
    rng = np.random.default_rng(seed)
    e57 = pye57.E57(str(path))
    n_scans = e57.scan_count
    counts = [e57.get_header(i).point_count for i in range(n_scans)]
    total = sum(counts)
    print(f"E57: {n_scans} scan(s), {total:,} points; poses: "
          f"{[e57.get_header(i).has_pose() for i in range(n_scans)]}")
    xyz_parts = []
    for i, n in enumerate(counts):
        scan = e57.read_scan(i, ignore_missing_fields=True, transform=True)
        keep = min(len(scan["cartesianX"]), round(max_points * n / total))
        idx = np.sort(rng.choice(len(scan["cartesianX"]), keep, replace=False))
        xyz_parts.append(np.stack([scan["cartesianX"][idx], scan["cartesianY"][idx], scan["cartesianZ"][idx]], 1))
        print(f"  scan {i}: kept {keep:,}/{n:,}")
        del scan
    pcd = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(np.concatenate(xyz_parts)))
    pcd.paint_uniform_color([0.9, 0.3, 0.1])  # the PC2Model sample is XYZ only
    return pcd


def load_ifc(path: Path) -> tuple[o3d.geometry.TriangleMesh, int]:
    model = ifcopenshell.open(str(path))
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    geom_iter = ifcopenshell.geom.iterator(
        settings, model, os.cpu_count() or 1,
        exclude=["IfcSpace", "IfcOpeningElement"],
    )
    verts, faces, offset, n_elements = [], [], 0, 0
    if geom_iter.initialize():
        while True:
            g = geom_iter.get().geometry
            v = np.asarray(g.verts, dtype=np.float64).reshape(-1, 3)
            f = np.asarray(g.faces, dtype=np.int32).reshape(-1, 3)
            if len(f):
                verts.append(v)
                faces.append(f + offset)
                offset += len(v)
                n_elements += 1
            if not geom_iter.next():
                break
    if not verts:
        raise RuntimeError(f"no tessellated geometry in {path}")
    mesh = o3d.geometry.TriangleMesh(
        o3d.utility.Vector3dVector(np.concatenate(verts)),
        o3d.utility.Vector3iVector(np.concatenate(faces)),
    )
    mesh.compute_vertex_normals()
    mesh.paint_uniform_color([0.62, 0.68, 0.78])
    return mesh, n_elements


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--e57", type=Path, default=DEFAULT_E57)
    ap.add_argument("--ifc", type=Path, default=DEFAULT_IFC)
    ap.add_argument("--max-points", type=int, default=2_000_000)
    ap.add_argument("--png", type=Path, default=ROOT / "docs/images/stage0-unaligned.png")
    ap.add_argument("--no-interactive", action="store_true")
    a = ap.parse_args()

    t = time.perf_counter()
    pcd = load_e57(a.e57, a.max_points)
    pts = np.asarray(pcd.points)
    print(f"scan: {len(pts):,} points shown; bbox {bbox_str(pts)}; {time.perf_counter() - t:.1f}s; peak RSS {peak_rss_gb():.2f} GB")

    t = time.perf_counter()
    mesh, n_el = load_ifc(a.ifc)
    mv = np.asarray(mesh.vertices)
    print(f"ifc: {n_el:,} elements, {len(mesh.triangles):,} triangles; bbox {bbox_str(mv)}; "
          f"{time.perf_counter() - t:.1f}s; peak RSS {peak_rss_gb():.2f} GB")

    vis = o3d.visualization.Visualizer()
    vis.create_window("scan vs BIM (unaligned)", 1280, 800)
    vis.add_geometry(pcd)
    vis.add_geometry(mesh)  # also resets the camera to fit all geometry
    vis.get_render_option().point_size = 1.5
    for _ in range(5):
        vis.poll_events()
        vis.update_renderer()
    scene = pcd.get_axis_aligned_bounding_box()
    scene += mesh.get_axis_aligned_bounding_box()
    scene_center, scene_extent, scene_zoom = scene.get_center(), scene.get_max_extent(), 0.7
    a.png.parent.mkdir(parents=True, exist_ok=True)
    vis.capture_screen_image(str(a.png))
    print(f"wrote {a.png}")
    # The two sit far apart, so also capture each one close up from the same window.
    view = vis.get_view_control()
    for name, geom in [("scan", pcd), ("ifc", mesh)]:
        view.set_lookat(geom.get_axis_aligned_bounding_box().get_center())
        view.set_zoom(0.7 * geom.get_axis_aligned_bounding_box().get_max_extent() / scene_extent)
        for _ in range(5):
            vis.poll_events()
            vis.update_renderer()
        png = a.png.with_name(f"{a.png.stem}-{name}{a.png.suffix}")
        vis.capture_screen_image(str(png))
        print(f"wrote {png}")
    view.set_lookat(scene_center)
    view.set_zoom(scene_zoom)
    print(f"peak RSS {peak_rss_gb():.2f} GB")
    if not a.no_interactive:
        vis.run()
    vis.destroy_window()


if __name__ == "__main__":
    main()

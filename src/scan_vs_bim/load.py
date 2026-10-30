"""Loaders: E57 scan -> Open3D point cloud, IFC model -> per-element meshes in world coordinates."""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import numpy as np
import open3d as o3d
import pye57

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ElementMesh:
    global_id: str
    ifc_class: str
    vertices: np.ndarray  # (n, 3) float64, world coordinates
    faces: np.ndarray  # (m, 3) int32, indices into vertices


def load_e57(path: Path, max_points: int, seed: int = 0) -> o3d.geometry.PointCloud:
    """XYZ only, scan poses applied, about max_points kept across scans (proportional, seeded)."""
    rng = np.random.default_rng(seed)
    e57 = pye57.E57(str(path))
    n_scans = e57.scan_count
    counts = [e57.get_header(i).point_count for i in range(n_scans)]
    total = sum(counts)
    log.info(f"E57: {n_scans} scan(s), {total:,} points; poses: "
             f"{[e57.get_header(i).has_pose() for i in range(n_scans)]}")
    xyz_parts = []
    for i, n in enumerate(counts):
        scan = e57.read_scan(i, ignore_missing_fields=True, transform=True)
        keep = min(len(scan["cartesianX"]), round(max_points * n / total))
        idx = np.sort(rng.choice(len(scan["cartesianX"]), keep, replace=False))
        xyz_parts.append(np.stack([scan["cartesianX"][idx], scan["cartesianY"][idx], scan["cartesianZ"][idx]], 1))
        log.info(f"  scan {i}: kept {keep:,}/{n:,}")
        del scan
    return o3d.geometry.PointCloud(o3d.utility.Vector3dVector(np.concatenate(xyz_parts)))


def load_e57_chunked(path: Path, max_points: int, seed: int = 0, chunk_points: int = 1_000_000) -> o3d.geometry.PointCloud:
    """Same points as `load_e57`, read `chunk_points` at a time so memory stays flat (load_e57 holds a whole scan,
    about 100 bytes per point at its peak). Files with invalid-point flags are not supported."""
    rng = np.random.default_rng(seed)
    e57 = pye57.E57(str(path))
    n_scans = e57.scan_count
    counts = [e57.get_header(i).point_count for i in range(n_scans)]
    total = sum(counts)
    parts = []
    for i, n in enumerate(counts):
        header = e57.get_header(i)
        if "cartesianInvalidState" in header.point_fields:
            raise NotImplementedError(f"{path}: invalid-point flags are not supported, use load_e57")
        keep_idx = np.sort(rng.choice(n, min(n, round(max_points * n / total)), replace=False))
        data, buffers = e57.make_buffers(["cartesianX", "cartesianY", "cartesianZ"], chunk_points)
        reader = header.points.reader(buffers)
        start = 0
        while (m := reader.read()) > 0:
            lo, hi = np.searchsorted(keep_idx, [start, start + m])
            rows = keep_idx[lo:hi] - start
            xyz = np.stack([data["cartesianX"][rows], data["cartesianY"][rows], data["cartesianZ"][rows]], 1)
            parts.append(e57.to_global(xyz, header.rotation, header.translation) if header.has_pose() else xyz)
            start += m
        reader.close()
        log.info(f"  scan {i}: kept {len(keep_idx):,}/{n:,}")
    return o3d.geometry.PointCloud(o3d.utility.Vector3dVector(np.concatenate(parts)))


def load_ifc_elements(path: Path, exclude=None, only_guids=None) -> list[ElementMesh]:
    """Tessellate the model, leaving out the IFC classes in `exclude` (default: IfcSpace, IfcOpeningElement).
    `only_guids` limits it to those GlobalIds (much faster on a big model); it cannot be combined with `exclude`."""
    if only_guids is not None and exclude is not None:
        raise ValueError("`exclude` has no effect with `only_guids`; pass one of them")
    if exclude is None:
        exclude = ("IfcSpace", "IfcOpeningElement")
    model = ifcopenshell.open(str(path))
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    if only_guids is None:
        geom_iter = ifcopenshell.geom.iterator(settings, model, os.cpu_count() or 1, exclude=list(exclude))
    else:
        geom_iter = ifcopenshell.geom.iterator(settings, model, os.cpu_count() or 1, include=[model.by_guid(g) for g in only_guids])
    elements = []
    if geom_iter.initialize():
        while True:
            shape = geom_iter.get()
            g = shape.geometry
            f = np.asarray(g.faces, dtype=np.int32).reshape(-1, 3)
            if len(f):
                v = np.asarray(g.verts, dtype=np.float64).reshape(-1, 3)
                elements.append(ElementMesh(shape.guid, shape.type, v, f))
            if not geom_iter.next():
                break
    if not elements:
        raise RuntimeError(f"no tessellated geometry in {path}")
    return elements


def merge_meshes(elements: list[ElementMesh]) -> o3d.geometry.TriangleMesh:
    offsets = np.cumsum([0] + [len(e.vertices) for e in elements[:-1]])
    mesh = o3d.geometry.TriangleMesh(
        o3d.utility.Vector3dVector(np.concatenate([e.vertices for e in elements])),
        o3d.utility.Vector3iVector(np.concatenate([e.faces + off for e, off in zip(elements, offsets)])),
    )
    mesh.compute_vertex_normals()
    return mesh


def load_ifc(path: Path) -> o3d.geometry.TriangleMesh:
    return merge_meshes(load_ifc_elements(path))

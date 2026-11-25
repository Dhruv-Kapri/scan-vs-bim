"""The helpers of the CRAS-room notebooks (03a, 03b, 03c), moved into scan_vs_bim.room (#33): the frame, the ICP target and the verdict stage's point cloud."""

from pathlib import Path
from typing import cast

import numpy as np
import open3d as o3d

from scan_vs_bim.load import ElementMesh
from scan_vs_bim.room import area_in_box, element_boxes, icp_target, patch_cloud, refine_from_recorded, transform_delta


def translation(x: float, y: float, z: float) -> np.ndarray:
    T = np.eye(4)
    T[:3, 3] = (x, y, z)
    return T


def rot_z(deg: float) -> np.ndarray:
    a = np.radians(deg)
    T = np.eye(4)
    T[:2, :2] = [[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]]
    return T


def block(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> ElementMesh:
    m = cast(o3d.geometry.TriangleMesh, o3d.geometry.TriangleMesh.create_box(x1 - x0, y1 - y0, z1 - z0).translate((x0, y0, z0)))
    return ElementMesh(global_id="g", ifc_class="IfcWall", vertices=np.asarray(m.vertices), faces=np.asarray(m.triangles))


def test_transform_delta_is_the_rotation_and_the_centroid_displacement_of_the_residual() -> None:
    T_b = rot_z(40) @ translation(5, -2, 1)  # the residual T_a @ inv(T_b) must not depend on T_b itself
    centroid = np.array([2.0, 0.0, 5.0])
    angle, shift = transform_delta(rot_z(3) @ T_b, T_b, centroid)
    assert np.isclose(angle, 3) and np.isclose(shift, 2 * 2.0 * np.sin(np.radians(1.5)))  # the chord of the arc the centroid sweeps, at radius 2 m
    angle, shift = transform_delta(translation(0.01, 0.02, 0) @ T_b, T_b, centroid)
    assert np.isclose(angle, 0, atol=1e-6) and np.isclose(shift, np.hypot(0.01, 0.02))


def test_patch_cloud_keeps_the_points_in_any_element_box_after_both_transforms_across_chunk_boundaries(tmp_path: Path) -> None:
    rng = np.random.default_rng(0)
    xyz = rng.integers(-6, 6, (50, 3)).astype(np.float32)
    cls = rng.integers(0, 30, 50).astype(np.uint8)
    cache = tmp_path / "cache.npz"
    np.savez(cache, xyz=xyz, cls=cls)
    T_rec, corr = translation(1, 0, 0), translation(0, 2, 0)
    # two boxes far apart in the refined frame: a point between them belongs to neither (per-element boxes, never their union)
    lo, hi = element_boxes([block(-4, -2, -4, -2, -4, -2), block(2, 4, 2, 4, 2, 4)], margin=0.5)
    moved = xyz + np.array([1, 2, 0], np.float32)
    expected = ((moved >= lo[0]) & (moved <= hi[0])).all(1) | ((moved >= lo[1]) & (moved <= hi[1])).all(1)
    in_union_box = ((moved >= lo.min(0)) & (moved <= hi.max(0))).all(1)
    assert 0 < expected.sum() < in_union_box.sum()  # the test discriminates: the union box would keep more
    out = patch_cloud(cache, T_rec, corr, lo, hi, chunk=7)  # 7 does not divide 50
    assert out.points.dtype == np.float32 and np.array_equal(out.points, moved[expected])
    assert np.array_equal(out.classes, cls[expected])
    assert out.in_crop is None and out.recorded is None


def test_patch_cloud_with_a_crop_also_keeps_and_flags_the_crop_points_in_the_recorded_frame(tmp_path: Path) -> None:
    rng = np.random.default_rng(1)
    xyz = rng.integers(-6, 6, (300, 3)).astype(np.float32)
    cache = tmp_path / "cache.npz"
    np.savez(cache, xyz=xyz, cls=np.arange(300) % 256)
    T_rec, corr = translation(1, 0, 0), translation(0, 2, 0)
    lo, hi = element_boxes([block(0, 4, 0, 4, 0, 4)], margin=0.5)
    crop_lo, crop_hi = np.array([-4.0, -4.0, -4.0]), np.array([-1.0, -1.0, -1.0])  # in the recorded frame (xyz + (1, 0, 0))
    rec, moved = xyz + np.array([1, 0, 0], np.float32), xyz + np.array([1, 2, 0], np.float32)
    in_crop = ((rec >= crop_lo) & (rec <= crop_hi)).all(1)
    in_box = ((moved >= lo[0]) & (moved <= hi[0])).all(1)
    assert (in_crop & ~in_box).any() and (in_box & ~in_crop).any()
    out = patch_cloud(cache, T_rec, corr, lo, hi, crop=(crop_lo, crop_hi), chunk=7)
    keep = in_crop | in_box
    assert out.in_crop is not None and out.recorded is not None
    assert np.array_equal(out.points, moved[keep]) and np.array_equal(out.classes, (np.flatnonzero(keep) % 256))
    assert np.array_equal(out.in_crop, in_crop[keep]) and np.array_equal(out.recorded, rec[keep])


def test_area_in_box_is_the_share_of_the_surface_inside_and_repeats_for_a_seed() -> None:
    slab = block(0, 2, 0, 1, 0, 1)  # surface 10 m2, half of it at x <= 1
    lo, hi = np.array([-1.0, -1.0, -1.0]), np.array([1.0, 2.0, 2.0])
    first = area_in_box([slab], lo, hi, seed=0)
    assert abs(first[0] - 0.5) < 0.05 and first == area_in_box([slab], lo, hi, seed=0)
    assert area_in_box([slab], lo - 5, hi + 5, seed=0) == [1.0]
    assert area_in_box([slab], lo + 10, hi + 10, seed=0) == [0.0]


def test_icp_target_keeps_the_samples_within_the_clip_of_the_box_and_flags_those_in_the_crop() -> None:
    wall = block(0, 10, 0, 1, 0, 1)
    box_lo, box_hi = np.array([0.0, 0.0, 0.0]), np.array([2.0, 1.0, 1.0])
    crop_lo, crop_hi = box_lo - 0.1, box_hi + 0.1
    target, in_crop = icp_target([wall], box_lo, box_hi, crop_lo, crop_hi, seed=0, n_samples=20_000, clip=0.3)
    q = np.asarray(target.points)
    assert 0 < len(q) < 20_000 and q[:, 0].max() <= 2.3 and target.has_normals()
    assert np.array_equal(in_crop, q[:, 0] <= 2.1) and 0 < in_crop.sum() < len(q)
    again, in_crop_again = icp_target([wall], box_lo, box_hi, crop_lo, crop_hi, seed=0, n_samples=20_000, clip=0.3)
    assert np.array_equal(np.asarray(again.points), q) and np.array_equal(in_crop_again, in_crop)


def test_refine_from_recorded_finds_a_small_known_offset_of_a_room() -> None:
    rng = np.random.default_rng(0)
    sides = [(0, 0.0), (0, 4.0), (1, 0.0), (1, 3.0), (2, 0.0), (2, 2.5)]  # the six faces of a 4 x 3 x 2.5 m room: (axis, position)
    extent = np.array([4.0, 3.0, 2.5])
    pts, normals = [], []
    for axis, pos in sides:
        p = rng.uniform(0, extent, (4000, 3))
        p[:, axis] = pos
        n = np.zeros(3)
        n[axis] = 1.0 if pos == 0 else -1.0
        pts.append(p)
        normals.append(np.tile(n, (4000, 1)))
    target = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(np.concatenate(pts)))
    target.normals = o3d.utility.Vector3dVector(np.concatenate(normals))
    offset = np.array([0.012, -0.008, 0.005])
    scan = np.concatenate(pts) + offset  # the scan sits `offset` off the model; the correction moves it back
    plain, robust = refine_from_recorded(scan, target, icp_dist=0.10, icp_fine_dist=0.05, tukey_k=0.02)
    assert np.allclose(robust.transformation[:3, 3], -offset, atol=1e-3) and np.allclose(robust.transformation[:3, :3], np.eye(3), atol=1e-3)
    assert plain.fitness > 0.9

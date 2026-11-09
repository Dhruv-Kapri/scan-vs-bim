from collections.abc import Sequence
from typing import Any

import numpy as np
import open3d as o3d
import pytest

from scan_vs_bim.pc2model import scale_of
from scan_vs_bim.register import refine_icp, refine_plan, voxel_schedule

# Gate thresholds (docs/roadmap.md) are 2 deg, 5 cm, 1 %; these tests ask for clearly tighter.
ROT_DEG: float = 0.3
CENTROID_M: float = 0.01
SCALE_REL: float = 0.003


def box_faces(lo: Sequence[float] | np.ndarray, hi: Sequence[float] | np.ndarray, n: int, rng: np.random.Generator) -> np.ndarray:
    """n points spread over the six faces of the box [lo, hi]."""
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    size = hi - lo
    areas = np.array([size[1] * size[2], size[1] * size[2], size[0] * size[2], size[0] * size[2], size[0] * size[1], size[0] * size[1]])
    face = rng.choice(6, n, p=areas / areas.sum())
    pts = lo + rng.random((n, 3)) * size
    axis, high = face // 2, face % 2
    pts[np.arange(n), axis] = np.where(high == 1, hi[axis], lo[axis])
    return pts


def room_points(n: int, rng: np.random.Generator) -> np.ndarray:
    """A 8 x 5 x 3 m room (inside faces) with two boxes of furniture, so no plane or axis is left free to slide along."""
    parts = [box_faces((0, 0, 0), (8, 5, 3), n // 2, rng),
             box_faces((1.0, 0.5, 0), (3.0, 1.5, 1.0), n // 4, rng),
             box_faces((5.5, 3.0, 0), (6.5, 4.0, 2.2), n // 4, rng)]
    return np.concatenate(parts)


def similarity(scale: float, rot_deg: float, axis: Sequence[float], t: Sequence[float]) -> np.ndarray:
    a = np.radians(rot_deg)
    k = np.asarray(axis, float) / np.linalg.norm(axis)
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    R = np.eye(3) + np.sin(a) * K + (1 - np.cos(a)) * K @ K
    T = np.eye(4)
    T[:3, :3], T[:3, 3] = scale * R, t
    return T


def cloud(pts: np.ndarray) -> o3d.geometry.PointCloud:
    return o3d.geometry.PointCloud(o3d.utility.Vector3dVector(pts))


def errors(T: np.ndarray, T_gt: np.ndarray, pts: np.ndarray) -> tuple[float, float, float]:
    A, B = T[:3, :3] / scale_of(T), T_gt[:3, :3] / scale_of(T_gt)
    rot = np.degrees(np.arccos(np.clip((np.trace(A.T @ B) - 1) / 2, -1, 1)))
    c = pts.mean(0)
    cen = np.linalg.norm(T[:3, :3] @ c + T[:3, 3] - (T_gt[:3, :3] @ c + T_gt[:3, 3]))
    return rot, cen, abs(scale_of(T) - scale_of(T_gt)) / scale_of(T_gt)


@pytest.fixture
def scene() -> tuple[o3d.geometry.PointCloud, o3d.geometry.PointCloud, np.ndarray, np.ndarray]:
    """model: the room; scan: an independent noisy sample of it, moved by inv(T_gt) so that T_gt maps the scan onto the model."""
    rng = np.random.default_rng(0)
    model = room_points(120_000, rng)
    T_gt = similarity(1.25, 20.0, (0.2, 0.3, 1.0), (4.0, -2.0, 1.0))
    scan_in_model = room_points(60_000, rng) + rng.normal(0, 0.003, (60_000, 3))
    scan = (scan_in_model - T_gt[:3, 3]) @ np.linalg.inv(T_gt[:3, :3]).T
    return cloud(model), cloud(scan), T_gt, scan


def coarse_error(T_gt: np.ndarray, scale_off: float) -> np.ndarray:
    """What a coarse stage leaves: a pose a little off, the scale off by `scale_off` (relative)."""
    return similarity(1 + scale_off, 1.5, (1.0, 0.5, 0.2), (0.12, -0.08, 0.05)) @ T_gt


def test_scale_stage_recovers_a_scaled_scan(scene: tuple[o3d.geometry.PointCloud, o3d.geometry.PointCloud, np.ndarray, np.ndarray]) -> None:
    model, scan, T_gt, pts = scene
    T = refine_icp(scan, model, coarse_error(T_gt, 0.05), scale_voxels=(0.4, 0.2, 0.1), rigid_voxels=(0.1, 0.05))
    rot, cen, scale = errors(T, T_gt, pts)
    assert rot <= ROT_DEG and cen <= CENTROID_M and scale <= SCALE_REL, (rot, cen, scale)


def test_rigid_stages_leave_the_scale_alone_and_fix_the_pose(scene: tuple[o3d.geometry.PointCloud, o3d.geometry.PointCloud, np.ndarray, np.ndarray]) -> None:
    model, scan, T_gt, pts = scene
    T0 = coarse_error(T_gt, 0.0)
    T = refine_icp(scan, model, T0, rigid_voxels=(0.2, 0.1, 0.05))
    assert scale_of(T) == pytest.approx(scale_of(T0), rel=1e-9)
    rot, cen, scale = errors(T, T_gt, pts)
    assert rot <= ROT_DEG and cen <= CENTROID_M and scale <= SCALE_REL, (rot, cen, scale)
    assert cen < errors(T0, T_gt, pts)[1] / 5   # the stages did the work: the start was ~15 cm off


def test_no_stages_is_a_no_op(scene: tuple[o3d.geometry.PointCloud, o3d.geometry.PointCloud, np.ndarray, np.ndarray]) -> None:
    model, scan, T_gt, _ = scene
    T0 = coarse_error(T_gt, 0.02)
    assert np.array_equal(refine_icp(scan, model, T0), T0)


def test_voxel_schedule_halves_down_to_the_floor() -> None:
    assert voxel_schedule(0.4, 0.05) == pytest.approx([0.2, 0.1, 0.05])
    assert voxel_schedule(0.4, 0.06) == pytest.approx([0.2, 0.1, 0.06])   # the last stage is the floor, never below it
    assert voxel_schedule(0.04, 0.05) == []   # already finer than the floor: no stage


@pytest.mark.parametrize(
    ("kwargs", "scale_voxels", "rigid_voxels"),
    [
        pytest.param({"scaled": False, "floor": 0.025}, [], [0.2, 0.1, 0.05, 0.025], id="unscaled"),
        # the defaults are the plan 05c chose and 05a runs (two scale stages, floor 2.5 cm): literals on purpose, so changing them fails here
        pytest.param({"scaled": True}, [0.2, 0.1], [0.1, 0.05, 0.025], id="scaled, defaults: rigid continues from the last scale voxel"),
        pytest.param({"scaled": True, "n_scale": 0, "floor": 0.025}, [], [0.2, 0.1, 0.05, 0.025], id="05c candidate R: no scale stages"),
        pytest.param({"scaled": True, "n_scale": 99, "floor": 0.05}, [0.2, 0.1, 0.05], [0.05], id="05c candidate S: scale at every stage"),
    ],
)
def test_refine_plan_scale_stages_then_rigid_stages_down_to_the_floor(kwargs: dict[str, Any], scale_voxels: list[float], rigid_voxels: list[float]) -> None:
    plan = refine_plan(0.4, **kwargs)
    assert plan["scale_voxels"] == pytest.approx(scale_voxels)
    assert plan["rigid_voxels"] == pytest.approx(rigid_voxels)


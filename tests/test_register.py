from collections.abc import Sequence
from typing import Any

import numpy as np
import open3d as o3d
import pytest

from scan_vs_bim import register
from scan_vs_bim.pc2model import scale_of
from scan_vs_bim.register import CENTROID_MAX_M, ROT_MAX_DEG, SCALE_MAX_REL, Draw, refine_icp, refine_plan, register_sample, score, voxel_schedule

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


def make_scene(scale: float, n_model: int = 120_000, n_scan: int = 60_000) -> tuple[o3d.geometry.PointCloud, o3d.geometry.PointCloud, np.ndarray, np.ndarray]:
    """model: the room; scan: an independent noisy sample of it, moved by inv(T_gt) so that T_gt (scale `scale`) maps the scan onto the model."""
    rng = np.random.default_rng(0)
    model = room_points(n_model, rng)
    T_gt = similarity(scale, 20.0, (0.2, 0.3, 1.0), (4.0, -2.0, 1.0))
    scan_in_model = room_points(n_scan, rng) + rng.normal(0, 0.003, (n_scan, 3))
    scan = (scan_in_model - T_gt[:3, 3]) @ np.linalg.inv(T_gt[:3, :3]).T
    return cloud(model), cloud(scan), T_gt, scan


@pytest.fixture
def scene() -> tuple[o3d.geometry.PointCloud, o3d.geometry.PointCloud, np.ndarray, np.ndarray]:
    return make_scene(1.25)


def coarse_error(T_gt: np.ndarray, scale_off: float) -> np.ndarray:
    """What a coarse stage leaves: a pose a little off, the scale off by `scale_off` (relative)."""
    return similarity(1 + scale_off, 1.5, (1.0, 0.5, 0.2), (0.12, -0.08, 0.05)) @ T_gt


def test_scale_stage_recovers_a_scaled_scan(scene: tuple[o3d.geometry.PointCloud, o3d.geometry.PointCloud, np.ndarray, np.ndarray]) -> None:
    model, scan, T_gt, pts = scene
    T = refine_icp(scan, model, coarse_error(T_gt, 0.05), scale_voxels=(0.4, 0.2, 0.1), rigid_voxels=(0.1, 0.05))
    sc = score(T, T_gt, pts)
    assert sc.rot_deg <= ROT_DEG and sc.centroid_m <= CENTROID_M and sc.scale_err <= SCALE_REL, sc


def test_rigid_stages_leave_the_scale_alone_and_fix_the_pose(scene: tuple[o3d.geometry.PointCloud, o3d.geometry.PointCloud, np.ndarray, np.ndarray]) -> None:
    model, scan, T_gt, pts = scene
    T0 = coarse_error(T_gt, 0.0)
    T = refine_icp(scan, model, T0, rigid_voxels=(0.2, 0.1, 0.05))
    assert scale_of(T) == pytest.approx(scale_of(T0), rel=1e-9)
    sc = score(T, T_gt, pts)
    assert sc.rot_deg <= ROT_DEG and sc.centroid_m <= CENTROID_M and sc.scale_err <= SCALE_REL, sc
    assert sc.centroid_m < score(T0, T_gt, pts).centroid_m / 5   # the stages did the work: the start was ~15 cm off


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
        # the defaults are the plan 05c chose and 05a runs (two scale stages, floor 2.5 cm): literals on purpose, so changing them fails here
        pytest.param({}, [0.2, 0.1], [0.1, 0.05, 0.025], id="defaults: rigid continues from the last scale voxel"),
        pytest.param({"n_scale": 0, "floor": 0.025}, [], [0.2, 0.1, 0.05, 0.025], id="05c candidate R: no scale stages"),
        pytest.param({"n_scale": 99, "floor": 0.05}, [0.2, 0.1, 0.05], [0.05], id="05c candidate S: scale at every stage"),
    ],
)
def test_refine_plan_scale_stages_then_rigid_stages_down_to_the_floor(kwargs: dict[str, Any], scale_voxels: list[float], rigid_voxels: list[float]) -> None:
    plan = refine_plan(0.4, **kwargs)
    assert plan["scale_voxels"] == pytest.approx(scale_voxels)
    assert plan["rigid_voxels"] == pytest.approx(rigid_voxels)


def test_register_sample_recovers_pose_and_scale_of_a_scaled_scan() -> None:
    model, scan, T_gt, pts = make_scene(1.25, 40_000, 20_000)
    result = register_sample(scan, model, voxel=0.08)
    sc = score(result.T, T_gt, pts)
    assert sc.rot_deg <= ROT_DEG and sc.centroid_m <= CENTROID_M and sc.scale_err <= SCALE_REL, sc
    assert [d.seed for d in result.draws] == [0, 1, 2, 3, 4]


def test_register_sample_fits_scale_on_an_unscaled_scan_and_stays_at_one() -> None:
    """ADR 0001: no scaled flag, the scale stages run on every sample, and a scan already at scale 1 must come out at 1 within 1 %."""
    assert refine_plan(0.08)["scale_voxels"]   # the scale stages are in the plan, so the scale is free to move
    model, scan, T_gt, pts = make_scene(1.0, 40_000, 20_000)
    result = register_sample(scan, model, voxel=0.08)
    sc = score(result.T, T_gt, pts)
    assert sc.scale_err <= SCALE_MAX_REL and sc.rot_deg <= ROT_DEG and sc.centroid_m <= CENTROID_M, sc


def test_register_sample_picks_the_best_coarse_fitness_and_the_earlier_seed_on_a_tie(monkeypatch: pytest.MonkeyPatch) -> None:
    fitness: dict[int, float] = {0: 0.5, 1: 0.9, 2: 0.7, 3: 0.9, 4: 0.2}   # seeds 1 and 3 tie for the best

    def T_of(seed: int) -> np.ndarray:   # a distinct, readable transform per seed: a shift of seed + 1 along x
        return similarity(1.0, 0.0, (0, 0, 1), (seed + 1.0, 0, 0))

    def fake_draw(src: Any, tgt: Any, src_f: Any, tgt_f: Any, voxel: float, seed: int) -> Draw:
        return Draw(seed, T_of(seed), fitness[seed], T_of(seed), fitness[seed])

    monkeypatch.setattr(register, "coarse_draw", fake_draw)
    monkeypatch.setattr(register, "preprocess", lambda pcd, voxel: (pcd, None))
    monkeypatch.setattr(register, "refine_icp", lambda scan, model, T, **plan: T)   # selection only: refinement passes through

    result = register_sample(cloud(np.eye(3)), cloud(np.eye(3)), voxel=0.1)   # not a point: its RMS radius is 0
    assert result.seed == 1
    assert np.array_equal(result.T, T_of(1))
    assert np.array_equal(result.T_seed0, T_of(0))   # seed 0's, not the winner's


def test_score_reports_each_error_of_a_hand_made_estimate() -> None:
    pts = np.array([[0.0, 0.0, 1.0], [0.0, 0.0, 3.0]])   # centroid on the z axis: a turn about z or a scale about the origin is easy to read off
    eye = np.eye(4)
    turn = score(similarity(1.0, 1.5, (0, 0, 1), (0, 0, 0)), eye, pts)
    assert (turn.rot_deg, turn.centroid_m, turn.scale_err) == pytest.approx((1.5, 0.0, 0.0))
    move = score(similarity(1.0, 0.0, (0, 0, 1), (0.03, 0, 0.04)), eye, pts)
    assert (move.rot_deg, move.centroid_m, move.scale_err) == pytest.approx((0.0, 0.05, 0.0))
    grow = score(similarity(1.02, 0.0, (0, 0, 1), (0, 0, 0)), eye, pts)
    assert (grow.rot_deg, grow.centroid_m, grow.scale_err) == pytest.approx((0.0, 0.04, 0.02))   # centroid (0, 0, 2) moves to (0, 0, 2.04)
    assert score(similarity(1.25, 20.0, (0.2, 0.3, 1.0), (4.0, -2.0, 1.0)), similarity(1.0, 20.0, (0.2, 0.3, 1.0), (4.0, -2.0, 1.0)), pts).scale_err == pytest.approx(0.25)   # relative to the truth


@pytest.mark.parametrize(
    ("criterion", "limit"),
    [("rotation", ROT_MAX_DEG), ("centroid", CENTROID_MAX_M), ("scale", SCALE_MAX_REL)],
)
def test_score_success_flips_at_each_threshold_and_is_inclusive_on_centroid(criterion: str, limit: float) -> None:
    pts = np.zeros((1, 3))

    def estimate(value: float) -> np.ndarray:   # exactly one error, `value`, the other two zero
        return {"rotation": similarity(1.0, value, (0, 0, 1), (0, 0, 0)),
                "centroid": similarity(1.0, 0.0, (0, 0, 1), (value, 0, 0)),
                "scale": similarity(1.0 + value, 0.0, (0, 0, 1), (0, 0, 0))}[criterion]

    assert score(estimate(limit - 1e-9), np.eye(4), pts).success
    assert not score(estimate(limit + 1e-9), np.eye(4), pts).success
    if criterion == "centroid":   # the only limit float arithmetic can hit exactly: a pure shift of (0.05, 0, 0); `<` would fail here
        assert score(estimate(limit), np.eye(4), pts).success

from collections.abc import Sequence
from typing import Any

import numpy as np
import open3d as o3d
import pytest

from scan_vs_bim import register
from scan_vs_bim.pc2model import scale_of
from scan_vs_bim.register import CENTROID_MAX_M, ROT_MAX_DEG, SCALE_MAX_REL, Draw, coarse_register, median_to_model, refine_icp, refine_plan, register_sample, score, succeeded, voxel_schedule

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


def test_coarse_register_hands_over_the_scaled_scan_and_the_draws_in_its_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    """The seam 05c uses (#33): the start scale is the RMS-radius ratio (1 if metric), the scan is copied and scaled, the draws stay in the scaled scan's frame."""
    fitness = {0: 0.5, 1: 0.9, 2: 0.7, 3: 0.8, 4: 0.2}
    monkeypatch.setattr(register, "coarse_draw", lambda src, tgt, src_f, tgt_f, voxel, seed: Draw(seed, np.eye(4), fitness[seed], similarity(1.0, 0.0, (0, 0, 1), (seed + 1.0, 0, 0)), fitness[seed]))
    monkeypatch.setattr(register, "preprocess", lambda pcd, voxel: (pcd, None))
    scan_pts = np.random.default_rng(0).random((50, 3))
    model, scan = cloud(2.0 * scan_pts), cloud(scan_pts)
    c = coarse_register(scan, model, voxel=1e-6)
    assert c.est_scale == pytest.approx(2.0) and np.array_equal(c.S, np.diag([c.est_scale] * 3 + [1.0]))
    assert np.allclose(np.asarray(c.scaled_scan.points), 2.0 * scan_pts) and np.array_equal(np.asarray(scan.points), scan_pts)   # a copy: the caller's scan is untouched
    assert (c.best.seed, c.first.seed) == (1, 0) and [d.seed for d in c.draws] == [0, 1, 2, 3, 4]
    assert np.array_equal(c.best.T, similarity(1.0, 0.0, (0, 0, 1), (2.0, 0, 0)))   # not composed with S
    assert coarse_register(scan, model, voxel=1e-6, metric=True).est_scale == 1.0


def test_median_to_model_is_the_median_distance_of_the_moved_points_to_the_mesh() -> None:
    """A big triangle in the plane z = 0; T lowers the points by 0.1, so their distances to it are 0.1, 0.2, 0.4 and the median is 0.2 (not the mean, 0.233)."""
    mesh = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector([[-9.0, -9.0, 0.0], [9.0, -9.0, 0.0], [0.0, 9.0, 0.0]]), o3d.utility.Vector3iVector([[0, 1, 2]]))
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    pts = np.array([[0.0, 0.0, 0.2], [1.0, 0.0, 0.3], [0.0, 1.0, 0.5]])
    assert median_to_model(scene, similarity(1.0, 0.0, (0, 0, 1), (0, 0, -0.1)), pts) == pytest.approx(0.2, abs=1e-6)


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


@pytest.mark.parametrize("worst", ["rot_deg", "centroid_m", "scale_err"])
def test_succeeded_is_inclusive_at_each_threshold(worst: str) -> None:
    """The shared rule (#33): each error <= its threshold, equality passes; one error just over fails with the other two at zero."""
    limit = {"rot_deg": ROT_MAX_DEG, "centroid_m": CENTROID_MAX_M, "scale_err": SCALE_MAX_REL}[worst]
    zero = {"rot_deg": 0.0, "centroid_m": 0.0, "scale_err": 0.0}
    assert succeeded(**zero | {worst: limit})
    assert not succeeded(**zero | {worst: limit * (1 + 1e-9)})


def test_apply_f32_is_the_float32_transform_the_verdict_notebooks_were_run_with() -> None:
    # 03a moved the CRAS cache (float32) with T cast to float32 and float32 out; 05b's patch counts must equal 03a's exactly (#42), so the package version is
    # held to that copy bit for bit, at model coordinates of tens of metres where float32 and float64 differ. Any input dtype comes out float32.
    rng = np.random.default_rng(0)
    c, s = np.cos(0.3), np.sin(0.3)
    T = np.array([[c, -s, 0, 12.345678], [s, c, 0, -4.2], [0, 0, 1, 1.5], [0, 0, 0, 1]])
    p32 = (rng.random((1000, 3)) * 20).astype(np.float32)
    copy_03a = (p32 @ T[:3, :3].T.astype(np.float32) + T[:3, 3].astype(np.float32)).astype(np.float32)
    got = register.apply_f32(T, p32)
    assert got.dtype == np.float32 and np.array_equal(got, copy_03a)
    assert not np.array_equal(got, register.apply(T, p32).astype(np.float32))   # the float64 route rounds differently: the test can tell them apart
    assert register.apply_f32(T, p32.astype(np.float64)).dtype == np.float32


def partial_scene() -> tuple[o3d.geometry.PointCloud, o3d.geometry.PointCloud, np.ndarray, np.ndarray]:
    """A scale-1 scene whose scan sees only the part of the room with x < 5.2 m, so the RMS-radius ratio is clearly not 1."""
    model, _, T_gt, _ = make_scene(1.0, 40_000, 20_000)
    pts_in_model = np.asarray(model.points)
    pts_in_model = pts_in_model[pts_in_model[:, 0] < 5.2]
    scan_pts = (pts_in_model - T_gt[:3, 3]) @ np.linalg.inv(T_gt[:3, :3]).T
    return model, cloud(scan_pts), T_gt, scan_pts


def test_register_sample_metric_keeps_the_scale_at_exactly_one_where_the_rms_start_is_off() -> None:
    """#52: a user-declared metric scan gets no RMS-radius start and no scale stages, so the scale is 1 to float precision."""
    model, scan, T_gt, pts = partial_scene()
    assert abs(register.rms_radius(model, 0.08) / register.rms_radius(scan, 0.08) - 1) > 0.05   # precondition: the estimate would be off
    result = register_sample(scan, model, voxel=0.08, metric=True)
    sc = score(result.T, T_gt, pts)
    assert abs(scale_of(result.T) - 1) < 1e-9
    assert sc.rot_deg <= ROT_DEG and sc.centroid_m <= CENTROID_M, sc


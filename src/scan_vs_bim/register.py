"""Registration as notebook 05a ran it, moved into the package (issue #37): FPFH + RANSAC + point-to-plane ICP over five seeds,
the draw with the highest coarse ICP fitness, then ICP passes that first fit a scale and then refine rigidly (issue #20), on every
sample, without the benchmark's scaled flag (issue #38, docs/adr/0001-fit-scale-on-every-sample.md), unless the caller declares the
scan metric (`metric=True`: rigid only, scale exactly 1, issue #52); and the score against a ground-truth transform (CONTEXT.md "Registration success")."""

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypedDict

import numpy as np
import open3d as o3d
import open3d.pipelines.registration as reg

from scan_vs_bim.load import seed_all
from scan_vs_bim.pc2model import scale_of

# 05a's values (02's before it): features, RANSAC, coarse ICP; distances are multiples of the voxel.
SEEDS: tuple[int, ...] = (0, 1, 2, 3, 4)   # one RANSAC draw per seed, reseeded right before RANSAC
NORMAL_RADIUS_X: float = 2.0   # normals for point-to-plane, as multiples of the stage's voxel
NORMAL_MAX_NN: int = 30
FPFH_RADIUS_X: float = 5.0
FPFH_MAX_NN: int = 100
RANSAC_MAX_ITER: int = 1_000_000
RANSAC_CONFIDENCE: float = 0.999
RANSAC_DISTANCE_X: float = 1.5
RANSAC_EDGE_RATIO: float = 0.9
RANSAC_MUTUAL_FILTER: bool = True
ICP_DISTANCE_X: float = 2.0
ICP_MAX_ITER: int = 100

# Registration success (CONTEXT.md): judgement calls fixed before the Phase 0.5 gate (docs/roadmap.md), not a standard.
ROT_MAX_DEG: float = 2.0
CENTROID_MAX_M: float = 0.05
SCALE_MAX_REL: float = 0.01


class RefinePlan(TypedDict):
    """Keyword arguments for `refine_icp`: the voxel size of each scale stage and of each rigid stage."""

    scale_voxels: list[float]
    rigid_voxels: list[float]


def refine_icp(
    src: o3d.geometry.PointCloud,
    tgt: o3d.geometry.PointCloud,
    T: np.ndarray,
    scale_voxels: Sequence[float] = (),
    rigid_voxels: Sequence[float] = (),
    dist_x: float = 2.0,
    max_iter: int = 50,
) -> np.ndarray:
    """Improve T (maps `src` onto `tgt`) with ICP stages, coarse to fine; one voxel size per stage.

    Scale stages come first: point-to-point ICP that also fits a uniform scale, so the scale comes from correspondences.
    Rigid stages follow: point-to-plane, which keeps whatever scale T has (it only adds a rigid move on the left).
    Each stage downsamples both clouds to its voxel and matches within dist_x voxels. No stages returns T unchanged.
    """
    est = reg.TransformationEstimationPointToPoint(with_scaling=True)
    for voxel in scale_voxels:
        T = _stage(src, tgt, T, voxel, dist_x, max_iter, est)
    for voxel in rigid_voxels:
        T = _stage(src, tgt, T, voxel, dist_x, max_iter, reg.TransformationEstimationPointToPlane(), normals=True)
    return T


def voxel_schedule(start: float, floor: float) -> list[float]:
    """Voxel sizes start/2, start/4, ... down to `floor`; the last stage is the floor itself. Empty if start is already <= floor."""
    out: list[float] = []
    v = start
    while v / 2 > floor:
        v /= 2
        out.append(v)
    return out + [floor] if start > floor else []


# Chosen on held-out PC2Model samples (notebook 05c, issue #20). Judgement calls, the gate's samples were not used.
FINE_FLOOR_M: float = 0.025   # finest ICP voxel: half the gate's 5 cm centroid threshold
SCALE_STAGES: int = 2       # scale-fitting stages (voxel/2, voxel/4); finer stages are rigid, at the scale those found


def refine_plan(voxel: float, n_scale: int = SCALE_STAGES, floor: float = FINE_FLOOR_M) -> RefinePlan:
    """The stages notebook 05a runs after the coarse ICP at `voxel`, on every sample (ADR 0001).

    n_scale scale stages (the coarsest of the schedule), then rigid stages from the last of them down to `floor`;
    n_scale=0 gives rigid stages only (05c's candidate R; `register_sample`'s metric mode, #52).
    """
    schedule = voxel_schedule(voxel, floor)
    if n_scale == 0:
        return RefinePlan(scale_voxels=[], rigid_voxels=schedule)
    n = min(n_scale, len(schedule))
    return RefinePlan(scale_voxels=schedule[:n], rigid_voxels=schedule[max(n - 1, 0):])


def _stage(
    src: o3d.geometry.PointCloud,
    tgt: o3d.geometry.PointCloud,
    T: np.ndarray,
    voxel: float,
    dist_x: float,
    max_iter: int,
    estimation: reg.TransformationEstimation,
    normals: bool = False,
) -> np.ndarray:
    s, t = src.voxel_down_sample(voxel), tgt.voxel_down_sample(voxel)
    if normals:
        t.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=NORMAL_RADIUS_X * voxel, max_nn=NORMAL_MAX_NN))
    return np.array(reg.registration_icp(s, t, dist_x * voxel, T, estimation, reg.ICPConvergenceCriteria(max_iteration=max_iter)).transformation)


def preprocess(pcd: o3d.geometry.PointCloud, voxel: float) -> tuple[o3d.geometry.PointCloud, reg.Feature]:
    """Voxel-downsample, estimate normals, compute FPFH (05a's preprocess)."""
    down = pcd.voxel_down_sample(voxel)
    down.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=NORMAL_RADIUS_X * voxel, max_nn=NORMAL_MAX_NN))
    fpfh = reg.compute_fpfh_feature(down, o3d.geometry.KDTreeSearchParamHybrid(radius=FPFH_RADIUS_X * voxel, max_nn=FPFH_MAX_NN))
    return down, fpfh


def apply(T: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Points (n, 3) moved by the 4x4 transform T."""
    return pts @ T[:3, :3].T + T[:3, 3]


def apply_f32(T: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Points (n, 3) moved by the 4x4 transform T in float32 (T cast to float32 first), float32 out whatever the input dtype: the CRAS notebooks' transform.
    Not `apply`: rounding differs, and 05b's patch counts must equal 03a's exactly."""
    return (pts @ T[:3, :3].T.astype(np.float32) + T[:3, 3].astype(np.float32)).astype(np.float32)


def rms_radius(pcd: o3d.geometry.PointCloud, voxel: float) -> float:
    """RMS distance of the voxel-downsampled cloud from its centroid (02's scale estimate uses the ratio of two)."""
    p = np.asarray(pcd.voxel_down_sample(voxel).points)
    return float(np.sqrt(((p - p.mean(0)) ** 2).sum(1).mean()))


@dataclass(frozen=True)
class Draw:
    """One coarse registration: RANSAC's transform and fitness, then point-to-plane ICP's transform and fitness."""

    seed: int
    T_ransac: np.ndarray
    ransac_fitness: float
    T: np.ndarray
    fitness: float


def coarse_draw(
    src: o3d.geometry.PointCloud,
    tgt: o3d.geometry.PointCloud,
    src_f: reg.Feature,
    tgt_f: reg.Feature,
    voxel: float,
    seed: int,
) -> Draw:
    """RANSAC on FPFH matches, then ICP (05a's register loop body).

    Reseeds numpy's and Open3D's global RNG with `seed` right before RANSAC, so the draw does not depend on what ran before;
    the global RNG state afterwards is that seed's.
    """
    seed_all(seed)
    ransac = reg.registration_ransac_based_on_feature_matching(
        src, tgt, src_f, tgt_f, RANSAC_MUTUAL_FILTER, RANSAC_DISTANCE_X * voxel,
        reg.TransformationEstimationPointToPoint(False), 3,
        [reg.CorrespondenceCheckerBasedOnEdgeLength(RANSAC_EDGE_RATIO),
         reg.CorrespondenceCheckerBasedOnDistance(RANSAC_DISTANCE_X * voxel)],
        reg.RANSACConvergenceCriteria(RANSAC_MAX_ITER, RANSAC_CONFIDENCE))
    icp = reg.registration_icp(src, tgt, ICP_DISTANCE_X * voxel, ransac.transformation,
                               reg.TransformationEstimationPointToPlane(),
                               reg.ICPConvergenceCriteria(max_iteration=ICP_MAX_ITER))
    return Draw(seed, np.array(ransac.transformation), float(ransac.fitness), np.array(icp.transformation), float(icp.fitness))


@dataclass(frozen=True)
class CoarseRegistration:
    """The front half of `register_sample` (#33): the scale start and the coarse draws, all in the scaled scan's frame."""

    est_scale: float   # the start scale: the RMS-radius ratio, 1.0 for a metric scan
    S: np.ndarray   # diag(est_scale, est_scale, est_scale, 1): scan -> scaled scan
    scaled_scan: o3d.geometry.PointCloud   # a copy of the scan multiplied by est_scale: what `refine_icp` continues from
    draws: tuple[Draw, ...]   # one per seed in SEEDS; T maps the scaled scan onto the model (compose with S for the original scan)
    best: Draw   # the highest coarse ICP fitness; ties: the earlier seed
    first: Draw   # seed 0's draw
    coarse_s: float   # seconds in preprocess + the coarse draws


def coarse_register(scan: o3d.geometry.PointCloud, model: o3d.geometry.PointCloud, voxel: float, metric: bool = False) -> CoarseRegistration:
    """The RMS-radius scale estimate (scale 1 if `metric`), the scan scaled by it (a copy), and a coarse draw per seed in SEEDS.

    Reseeds numpy's and Open3D's global RNG once per seed (see `coarse_draw`), so the global RNG state afterwards is the last seed's.
    """
    est_scale = 1.0 if metric else rms_radius(model, voxel) / rms_radius(scan, voxel)
    S = np.diag([est_scale, est_scale, est_scale, 1.0])
    scaled_scan = o3d.geometry.PointCloud(scan)
    scaled_scan.transform(S)   # in place

    t0 = time.perf_counter()
    src, src_f = preprocess(scaled_scan, voxel)
    tgt, tgt_f = preprocess(model, voxel)
    draws = tuple(coarse_draw(src, tgt, src_f, tgt_f, voxel, seed) for seed in SEEDS)
    coarse_s = time.perf_counter() - t0
    return CoarseRegistration(est_scale, S, scaled_scan, draws, max(draws, key=lambda d: d.fitness), draws[0], coarse_s)


@dataclass(frozen=True)
class SampleRegistration:
    """05a's registration of one sample: every transform maps the original (unscaled) scan onto the model."""

    T: np.ndarray   # the picked draw, refined
    seed: int   # the picked draw's seed
    draws: tuple[Draw, ...]   # one coarse draw per seed in SEEDS
    T_seed0: np.ndarray   # seed 0, refined (context only)
    coarse_s: float   # seconds in preprocess + the coarse draws
    refine_s: float   # seconds in the refinement


def register_sample(scan: o3d.geometry.PointCloud, model: o3d.geometry.PointCloud, voxel: float, metric: bool = False) -> SampleRegistration:
    """05a's registration on every sample, whatever its true scale (ADR 0001): `coarse_register` (RMS-radius scale estimate as the start, a coarse
    draw per seed, the best coarse ICP fitness picked), then the refinement of the picked draw and of seed 0 (scale-fitting stages, then rigid ones).

    metric=True is the user's declaration that the scan is already in the model's units (a real scanner): no RMS-radius estimate (start
    scale 1) and rigid stages only, so the result's scale is exactly 1 (ADR 0001, #52). The benchmark leaves it False: a per-sample flag
    would be the oracle again.

    Reseeds numpy's and Open3D's global RNG (once per seed, see `coarse_draw`), so the global RNG state afterwards is the last seed's.
    """
    c = coarse_register(scan, model, voxel, metric)
    draws = [Draw(d.seed, d.T_ransac @ c.S, d.ransac_fitness, d.T @ c.S, d.fitness) for d in c.draws]   # compose: scale first, then the rigid transform

    t1 = time.perf_counter()
    plan = refine_plan(voxel, n_scale=0 if metric else SCALE_STAGES)
    T_best = refine_icp(c.scaled_scan, model, c.best.T, **plan) @ c.S
    T_seed0 = T_best if c.best is c.first else refine_icp(c.scaled_scan, model, c.first.T, **plan) @ c.S
    refine_s = time.perf_counter() - t1
    return SampleRegistration(T_best, c.best.seed, tuple(draws), T_seed0, c.coarse_s, refine_s)


def median_to_model(scene: o3d.t.geometry.RaycastingScene, T: np.ndarray, pts: np.ndarray) -> float:
    """Median distance from `pts` moved by T to the mesh in `scene` (05a's and 02's registration residual and direction check, #33); float32, as they were."""
    moved = o3d.core.Tensor(apply(T, pts).astype(np.float32), o3d.core.float32, o3d.core.Device("CPU:0"))
    return float(np.median(scene.compute_distance(moved).numpy()))


def rotation_error_deg(T_est: np.ndarray, T_gt: np.ndarray) -> float:
    """Geodesic angle between the two rotations; the scale is divided out of each 3x3 block first (05a's)."""
    A, B = T_est[:3, :3] / scale_of(T_est), T_gt[:3, :3] / scale_of(T_gt)
    return float(np.degrees(np.arccos(np.clip((np.trace(A.T @ B) - 1) / 2, -1, 1))))


def centroid_error(T_est: np.ndarray, T_gt: np.ndarray, pts: np.ndarray) -> float:
    """Distance between where T_est and T_gt put the centroid of `pts` (CONTEXT.md "Centroid error")."""
    c = pts.mean(0)
    return float(np.linalg.norm(apply(T_est, c) - apply(T_gt, c)))


@dataclass(frozen=True)
class Score:
    """An estimate against the ground truth: the three errors and whether all are within the thresholds."""

    rot_deg: float
    centroid_m: float
    scale_err: float   # relative: |s_est - s_gt| / s_gt
    success: bool


def succeeded(rot_deg: float, centroid_m: float, scale_err: float) -> bool:
    """CONTEXT.md "Registration success": all three errors within their thresholds (equal passes). `score` uses it; 05b re-derives 05a's flags with it (#33)."""
    return rot_deg <= ROT_MAX_DEG and centroid_m <= CENTROID_MAX_M and scale_err <= SCALE_MAX_REL


def score(T_est: np.ndarray, T_gt: np.ndarray, pts: np.ndarray) -> Score:
    """Rotation, centroid and relative scale error of T_est against T_gt over the scan points `pts`; success is `succeeded`."""
    rot, cen = rotation_error_deg(T_est, T_gt), centroid_error(T_est, T_gt, pts)
    s_gt = scale_of(T_gt)
    scale_err = abs(scale_of(T_est) - s_gt) / s_gt
    return Score(rot, cen, scale_err, succeeded(rot, cen, scale_err))

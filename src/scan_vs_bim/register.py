"""Registration refinement: finer ICP passes after the coarse RANSAC + ICP, with an optional scale-aware stage (issue #20)."""

from collections.abc import Sequence
from typing import TypedDict

import numpy as np
import open3d as o3d
import open3d.pipelines.registration as reg

NORMAL_RADIUS_X: float = 2.0   # normals for point-to-plane, as multiples of the stage's voxel (05a's values)
NORMAL_MAX_NN: int = 30


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


def refine_plan(voxel: float, scaled: bool, n_scale: int = SCALE_STAGES, floor: float = FINE_FLOOR_M) -> RefinePlan:
    """The stages notebook 05a runs after the coarse ICP at `voxel`: scale stages only on a sample flagged scaled.

    n_scale scale stages (the coarsest of the schedule), then rigid stages from the last of them down to `floor`;
    n_scale=0 or an unscaled sample gives rigid stages only.
    """
    schedule = voxel_schedule(voxel, floor)
    if not scaled or n_scale == 0:
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

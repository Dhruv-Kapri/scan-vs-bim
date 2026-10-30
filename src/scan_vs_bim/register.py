"""Registration refinement: finer ICP passes after the coarse RANSAC + ICP, with an optional scale-aware stage (issue #20)."""

import numpy as np
import open3d as o3d

reg = o3d.pipelines.registration

NORMAL_RADIUS_X, NORMAL_MAX_NN = 2.0, 30   # normals for point-to-plane, as multiples of the stage's voxel (05a's values)


def refine_icp(src, tgt, T, scale_voxels=(), rigid_voxels=(), dist_x=2.0, max_iter=50):
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


def voxel_schedule(start, floor):
    """Voxel sizes start/2, start/4, ... down to `floor`; the last stage is the floor itself. Empty if start is already <= floor."""
    out, v = [], start
    while v / 2 > floor:
        v /= 2
        out.append(v)
    return out + [floor] if start > floor else []


# Chosen on held-out PC2Model samples (notebook 05c, issue #20). Judgement calls, the gate's samples were not used.
FINE_FLOOR_M = 0.025   # finest ICP voxel: half the gate's 5 cm centroid threshold
SCALE_STAGES = 2       # scale-fitting stages (voxel/2, voxel/4); finer stages are rigid, at the scale those found


def refine_plan(voxel, scaled):
    """The stages notebook 05a runs after the coarse ICP at `voxel`: scale stages only on a sample flagged scaled."""
    schedule = voxel_schedule(voxel, FINE_FLOOR_M)
    if not scaled:
        return dict(scale_voxels=[], rigid_voxels=schedule)
    return dict(scale_voxels=schedule[:SCALE_STAGES], rigid_voxels=schedule[SCALE_STAGES - 1:])


def _stage(src, tgt, T, voxel, dist_x, max_iter, estimation, normals=False):
    s, t = src.voxel_down_sample(voxel), tgt.voxel_down_sample(voxel)
    if normals:
        t.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=NORMAL_RADIUS_X * voxel, max_nn=NORMAL_MAX_NN))
    return np.array(reg.registration_icp(s, t, dist_x * voxel, T, estimation, reg.ICPConvergenceCriteria(max_iteration=max_iter)).transformation)

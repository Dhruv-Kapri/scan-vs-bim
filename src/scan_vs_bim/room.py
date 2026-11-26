"""A CRAS room's frame and verdict-stage cloud: the helpers notebooks 03a, 03b and 03c each carried a copy of until #33.

The scan is already in the model frame under the recorded transform (01's `T_REC`); `refine_from_recorded` refines it by ICP against `icp_target`'s points sampled on the room's elements, and
`transform_delta` says how far two such transforms are apart. `patch_cloud` then streams the 1 cm scan cache once more, after the correction (#31), and keeps the points near the elements'
bounding boxes (#23): the cloud the verdicts of `scan_vs_bim.compare` are computed from. `area_in_box` is the informational share of an element's surface in a box.
All of it is the notebooks' code, moved unchanged (the same seeds, casts and chunking: the notebooks' outputs must not change); the notebooks pass their constants as arguments.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Final, NamedTuple

import numpy as np
import open3d as o3d
import open3d.pipelines.registration as reg

from scan_vs_bim.compare import Mesh, mesh_of
from scan_vs_bim.load import ElementMesh, merge_meshes
from scan_vs_bim.register import apply_f32

__all__ = ["CHUNK", "PatchCloud", "area_in_box", "element_boxes", "icp_target", "patch_cloud", "refine_from_recorded", "transform_delta"]

CHUNK: Final[int] = 4_000_000  # scan points transformed at a time when streaming the cache (the peak-memory knob of the CRAS notebooks)


def transform_delta(T_a: np.ndarray, T_b: np.ndarray, centroid: np.ndarray) -> tuple[float, float]:
    """How far apart two scan -> model transforms are: the rotation (deg) between them, and the displacement (m) of the room `centroid`.
    The residual T_a @ inv(T_b) is the identity when they agree (00's errors())."""
    residual = T_a @ np.linalg.inv(T_b)
    angle = np.degrees(np.arccos(np.clip((np.trace(residual[:3, :3]) - 1) / 2, -1, 1)))
    return float(angle), float(np.linalg.norm(residual[:3, :3] @ centroid + residual[:3, 3] - centroid))


def icp_target(
    els: Sequence[ElementMesh], box_lo: np.ndarray, box_hi: np.ndarray, crop_lo: np.ndarray, crop_hi: np.ndarray, seed: int, n_samples: int, clip: float
) -> tuple[o3d.geometry.PointCloud, np.ndarray]:
    """ICP's target: `n_samples` points sampled on the elements (all faces, with the triangles' normals; Open3D's RNG seeded with `seed`), kept within `clip` of the room box [box_lo, box_hi].
    Also the boolean mask over the kept points of those inside the scan crop [crop_lo, crop_hi]: 03a's RANSAC points (`target.select_by_index(np.flatnonzero(mask))`) and,
    as their mean, the room centroid where rotation errors are turned into millimetres."""
    o3d.utility.random.seed(seed)
    sampled = merge_meshes(list(els)).sample_points_uniformly(n_samples, use_triangle_normal=True)
    q = np.asarray(sampled.points)
    target = sampled.select_by_index(np.flatnonzero(((q >= box_lo - clip) & (q <= box_hi + clip)).all(1)).tolist())
    q = np.asarray(target.points)
    return target, ((q >= crop_lo) & (q <= crop_hi)).all(1)


def refine_from_recorded(points: np.ndarray, target: o3d.geometry.PointCloud, icp_dist: float, icp_fine_dist: float, tukey_k: float) -> tuple[reg.RegistrationResult, reg.RegistrationResult]:
    """ICP from the recorded transform: the scan `points` are already in the model frame under it, so ICP starts at the identity and its result is the correction in the model frame
    (T_refined = correction @ T_REC). Plain point-to-plane ICP within `icp_dist`, then a Tukey-robust pass within `icp_fine_dist` (residuals beyond `tukey_k` get no weight). Returns both results."""
    src = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points.astype(np.float64)))
    est = reg.TransformationEstimationPointToPlane
    plain = reg.registration_icp(src, target, icp_dist, np.eye(4), est(), reg.ICPConvergenceCriteria(1e-8, 1e-8, 50))
    robust = reg.registration_icp(src, target, icp_fine_dist, plain.transformation, est(reg.TukeyLoss(tukey_k)), reg.ICPConvergenceCriteria(1e-8, 1e-8, 100))
    return plain, robust


def area_in_box(
    els: Sequence[Mesh], lo: np.ndarray, hi: np.ndarray, seed: int, per_m2: float = 200, n_min: int = 2000, n_max: int = 200_000
) -> list[float]:
    """The share of each element's surface inside the box [lo, hi], from surface samples (`per_m2` per m2 of the surface, at least `n_min` and at most `n_max`; Open3D's RNG seeded with `seed`
    once, so the samples depend on the seed and the meshes only). Informational in 03a (`area_in_box_frac` in the CSV): it drives no verdict. A share above 0 means some surface lies in the box:
    03a's scope of the padded variant is the elements with a share above 0 in the box padded by PAD, from the same samples."""
    o3d.utility.random.seed(seed)
    out: list[float] = []
    for e in els:
        m = mesh_of(e)
        pts = np.asarray(m.sample_points_uniformly(int(np.clip(m.get_surface_area() * per_m2, n_min, n_max))).points)
        out.append(float(((pts >= lo) & (pts <= hi)).all(1).mean()))
    return out


def element_boxes(els: Sequence[Mesh], margin: float) -> tuple[np.ndarray, np.ndarray]:
    """The bounding box of every element grown by `margin` on each side: (lo, hi), float32, one row per element: the per-element boxes `patch_cloud` cuts with."""
    lo = np.array([e.vertices.min(0) - margin for e in els], np.float32)
    hi = np.array([e.vertices.max(0) + margin for e in els], np.float32)
    return lo, hi


class PatchCloud(NamedTuple):
    points: np.ndarray  # model frame, refined (corr @ T_REC), float32
    classes: np.ndarray  # the scan class of each point
    in_crop: np.ndarray | None  # whether the point lies in the crop in the recorded frame; None without a crop
    recorded: np.ndarray | None  # the points in the recorded frame (T_REC only); None without a crop


def patch_cloud(
    cache: Path, T_rec: np.ndarray, corr: np.ndarray, lo_b: np.ndarray, hi_b: np.ndarray, crop: tuple[np.ndarray, np.ndarray] | None = None, chunk: int = CHUNK
) -> PatchCloud:
    """The verdict stage's points (#23, #31): the 1 cm scan cache (`xyz`, `cls`) in the model frame under the recorded transform `T_rec` and then the ICP correction `corr` (model frame:
    T_refined = corr @ T_rec), `chunk` points at a time (`apply_f32`), those within the per-element boxes [lo_b, hi_b] (`element_boxes`; never their union: the floor slab alone spans the
    building). The boxes are applied to the corrected points, so they need no allowance for the correction.
    With `crop` = (lo, hi) in the RECORDED frame (03b: the crop is cut before the correction, as ICP's input) the points in it stay in the cloud too (the occlusion measure keeps the room's
    clutter), `in_crop` flags them, and `recorded` holds the same points before the correction (03b's dragged frames apply their own correction to these, so their coordinates are not rounded twice).
    Without a crop (03a, 03c) those two are None and not kept."""
    data = np.load(cache)
    xyz, cls_all = data["xyz"], data["cls"]
    parts: list[np.ndarray] = []
    class_parts: list[np.ndarray] = []
    crop_parts: list[np.ndarray] = []
    rec_parts: list[np.ndarray] = []
    for i in range(0, len(xyz), chunk):
        p_rec = apply_f32(T_rec, xyz[i:i + chunk])
        p = apply_f32(corr, p_rec)
        if crop is None:
            near = np.zeros(len(p), bool)
        else:
            in_crop = ((p_rec >= crop[0]) & (p_rec <= crop[1])).all(1)
            near = in_crop.copy()
        for lo, hi in zip(lo_b, hi_b):
            near |= ((p >= lo) & (p <= hi)).all(1)
        parts.append(p[near])
        class_parts.append(cls_all[i:i + chunk][near])
        if crop is not None:
            crop_parts.append(in_crop[near])
            rec_parts.append(p_rec[near])
    if crop is None:
        return PatchCloud(np.concatenate(parts), np.concatenate(class_parts), None, None)
    return PatchCloud(np.concatenate(parts), np.concatenate(class_parts), np.concatenate(crop_parts), np.concatenate(rec_parts))

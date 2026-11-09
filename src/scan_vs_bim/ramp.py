"""Gradient of a surface height over the plan: the seam of notebook 03d (why does the scan floor ramp, issue #26)."""

from collections.abc import Hashable, Iterator, Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Gradient:
    gx: float  # slope in x (m per m)
    gy: float  # slope in y (m per m)
    intercepts: dict[Hashable, float]  # per group: the fitted value at x = y = 0 (m)
    rms: float  # of the residuals about the fitted planes (m)
    residuals: np.ndarray  # value minus its group's fitted plane, per input position (m)


def plane_gradient(x: np.ndarray, y: np.ndarray, values: np.ndarray, groups: Sequence[Hashable] | np.ndarray | None = None) -> Gradient:
    """Least-squares plane `value = intercept[group] + gx * x + gy * y`: one intercept per group, one slope shared by all.
    Without `groups` there is one intercept. Raises ValueError when the positions, once each group's own mean is removed, lie on a
    line (or a point): the slope across the line is then not determined."""
    x, y, values = (np.asarray(a, dtype=float) for a in (x, y, values))
    labels = np.zeros(len(x), dtype=int) if groups is None else np.asarray(groups)
    keys = np.unique(labels)
    mean_x, mean_y, mean_v = (np.empty(len(x)) for _ in range(3))
    for k in keys:  # remove each group's own mean: the intercepts drop out, the shared slope is what is left
        m = labels == k
        mean_x[m], mean_y[m], mean_v[m] = x[m].mean(), y[m].mean(), values[m].mean()
    design = np.column_stack([x - mean_x, y - mean_y])
    sv = np.linalg.svd(design, compute_uv=False)
    if sv[-1] <= 1e-9 * max(sv[0], 1e-300):
        raise ValueError("the positions lie on a line (within each group): the gradient across it is not determined")
    slope, *_ = np.linalg.lstsq(design, values - mean_v, rcond=None)
    residuals = values - mean_v - design @ slope
    intercepts = {k.item(): float(mean_v[labels == k][0] - slope[0] * mean_x[labels == k][0] - slope[1] * mean_y[labels == k][0]) for k in keys}
    return Gradient(float(slope[0]), float(slope[1]), intercepts, float(np.sqrt(np.mean(residuals**2))), residuals)


def block_resamples(x: np.ndarray, y: np.ndarray, block: float, n_boot: int, seed: int) -> Iterator[np.ndarray]:
    """Bootstrap resamples of position indices, made of whole `block` x `block` squares drawn with replacement (seeded).
    Neighbouring cells of a smooth surface are alike, so resampling single cells would make a confidence interval too narrow."""
    square = np.column_stack([np.floor(np.asarray(x) / block), np.floor(np.asarray(y) / block)])
    _, inverse = np.unique(square, axis=0, return_inverse=True)
    members = [np.flatnonzero(inverse.ravel() == b) for b in range(inverse.max() + 1)]
    rng = np.random.default_rng(seed)
    for _ in range(n_boot):
        yield np.concatenate([members[b] for b in rng.integers(0, len(members), len(members))])

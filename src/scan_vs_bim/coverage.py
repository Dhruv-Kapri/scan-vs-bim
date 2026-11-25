"""#30's coverage measure (share of an element's face that scan points cover). Issue #43 rejected its rule; kept so notebooks 03c and 03c_room_a share one copy and stay reproducible. No pipeline code uses it."""

import numpy as np


def face_coverage(points: np.ndarray, vertices: np.ndarray, faces: np.ndarray, axis: int, cell: float) -> float:
    """Share of an element's face that the points cover, seen along `axis` (issue #30).

    The triangles `faces` (indices into `vertices`) and the points are projected onto the two coordinates other than `axis`. A square lattice of side `cell`,
    anchored at multiples of `cell` (so a cell is the same cell whatever the data), divides the plane; the face cells are those whose centre lies inside at least one
    projected triangle (a triangle that is edge-on in the projection covers nothing, and the two broad faces of a partition, which project onto the same area, count once).
    Returns the share of face cells that hold at least one point; points outside the face cells are ignored. 0.0 if there are no face cells or no points.
    """
    points = np.asarray(points, np.float64)
    keep = [k for k in range(3) if k != axis]
    tri = np.asarray(vertices, np.float64)[np.asarray(faces, int)][:, :, keep] if len(faces) else np.zeros((0, 3, 2))
    if len(points) == 0 or len(tri) == 0:
        return 0.0
    k_lo = np.floor(tri.min(axis=(0, 1)) / cell).astype(int)  # the face's own bounding cells: the grid never spans more than the face
    shape = np.floor(tri.max(axis=(0, 1)) / cell).astype(int) - k_lo + 1
    face = np.zeros(shape, bool)
    for a, b, c in tri:  # one triangle at a time over its own bounding cells: memory stays at one grid plus one triangle's cells
        det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(det) < 1e-12:
            continue
        lo, hi = np.ceil(np.minimum(np.minimum(a, b), c) / cell - 0.5).astype(int), np.floor(np.maximum(np.maximum(a, b), c) / cell - 0.5).astype(int)
        if (hi < lo).any():
            continue
        gx, gy = np.meshgrid(np.arange(lo[0], hi[0] + 1), np.arange(lo[1], hi[1] + 1), indexing="ij")
        cx, cy = (gx + 0.5) * cell, (gy + 0.5) * cell
        w0 = ((b[1] - c[1]) * (cx - c[0]) + (c[0] - b[0]) * (cy - c[1])) / det
        w1 = ((c[1] - a[1]) * (cx - c[0]) + (a[0] - c[0]) * (cy - c[1])) / det
        inside = (w0 >= -1e-9) & (w1 >= -1e-9) & (1 - w0 - w1 >= -1e-9)
        face[gx[inside] - k_lo[0], gy[inside] - k_lo[1]] = True
    if not face.any():
        return 0.0
    j = np.floor(points[:, keep] / cell).astype(int) - k_lo
    on_grid = ((j >= 0) & (j < shape)).all(1)
    j = j[on_grid]
    j = j[face[j[:, 0], j[:, 1]]]  # points over a face cell
    filled = np.zeros(shape, bool)
    filled[j[:, 0], j[:, 1]] = True
    return float(filled.sum() / face.sum())

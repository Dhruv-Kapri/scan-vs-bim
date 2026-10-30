"""Pure geometry for the compare stage (03a/03b/03c): which scan points lie over an element's own face.

A point within BAND of an element is measured to the element's surface, but near the element's edges the nearest point of the surface is the
edge itself, so a point past the end of a wall, or above its top, reads as an offset that is really a distance to the edge. Such a point belongs to
whatever stands beyond the edge (a neighbour, the ceiling above a wall), not to the element's face. `over_own_face` finds the points whose projection
onto the element's own face lies on that face (issue #20: the own-face patch).
"""

import numpy as np
import open3d as o3d

NUMERIC_TOL = 1e-4  # m: float32 closest-point noise; a point that projects onto the face is within this of its foot point's plane


def _unit_normals(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    tri = vertices[faces]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(n, axis=1, keepdims=True)
    return n / np.where(length == 0, 1, length)


def aligned_faces(vertices: np.ndarray, faces: np.ndarray, axis: int, among: np.ndarray | None = None, cos: float = 0.99) -> np.ndarray:
    """Boolean per triangle: its normal lies along +-`axis` (|cos| > `cos`), i.e. it is on one of the element's two broad faces across that axis.
    `among` (boolean per triangle) restricts the choice, e.g. to a wall's room-facing triangles."""
    m = np.abs(_unit_normals(vertices, faces)[:, axis]) > cos
    return m if among is None else m & among


def over_own_face(points: np.ndarray, vertices: np.ndarray, faces: np.ndarray, margin: float = 0.0) -> np.ndarray:
    """Boolean per point: does it lie over the element's own face?

    `faces` are the triangles (indices into `vertices`) that make up the face or faces (a wall's room-facing broad faces, a slab's top and bottom).
    A point is over them if its nearest point on them is reached by moving along the surface normal, that is, if its in-plane distance to the face
    (distance from the foot point, measured in the face's plane) is at most `margin` (+ float noise). The distance in front of or behind the face does not matter.
    `margin` is the edge allowance: 0 keeps only points that project onto the face; a few mm keeps the edge itself in spite of scan noise.
    """
    points = np.asarray(points)
    if len(points) == 0:
        return np.zeros(0, bool)
    sub = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(np.asarray(vertices, np.float64)), o3d.utility.Vector3iVector(np.asarray(faces, np.int32)))
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(sub))
    normals = _unit_normals(np.asarray(vertices, np.float64), np.asarray(faces))
    out = np.empty(len(points), bool)
    for i in range(0, len(points), 1_000_000):
        p = np.ascontiguousarray(points[i:i + 1_000_000], dtype=np.float32)
        r = scene.compute_closest_points(o3d.core.Tensor(p))
        d = p.astype(np.float64) - r["points"].numpy()
        n = normals[r["primitive_ids"].numpy()]
        lateral = np.linalg.norm(d - (d * n).sum(1, keepdims=True) * n, axis=1)
        out[i:i + 1_000_000] = lateral <= margin + NUMERIC_TOL
    return out

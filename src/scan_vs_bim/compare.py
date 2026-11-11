"""The compare stage: per-element verdicts (`judge_elements`, moved from notebook 03a, issue #40) and the geometry under them.

`judge_elements` takes the element meshes, the scan points, a use mask and the rule constants (`VerdictRules`; `RULES` holds the values 03a used) and returns one verdict row per element.
03b, 03c and 05b still carry their own copies of this logic. Below it: which scan points lie over an element's own face.

A point within BAND of an element is measured to the element's surface, but near the element's edges the nearest point of the surface is the
edge itself, so a point past the end of a wall, or above its top, reads as an offset that is really a distance to the edge. Such a point belongs to
whatever stands beyond the edge (a neighbour, the ceiling above a wall), not to the element's face. `over_own_face` finds the points whose projection
onto the element's own face lies on that face (issue #20: the own-face patch).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Protocol, TypedDict

import numpy as np
import open3d as o3d

NUMERIC_TOL: float = 1e-4  # m: float32 closest-point noise; a point that projects onto the face is within this of its foot point's plane


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
    if len(points) == 0 or len(faces) == 0:
        return np.zeros(len(points), bool)
    sub = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(np.asarray(vertices, np.float64)), o3d.utility.Vector3iVector(np.asarray(faces, np.int32)))
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(sub))
    normals = _unit_normals(np.asarray(vertices, np.float64), np.asarray(faces))
    out = np.empty(len(points), bool)
    for i in range(0, len(points), 1_000_000):
        p = np.ascontiguousarray(points[i:i + 1_000_000], dtype=np.float32)
        # Explicit dtype/device: the same as the runtime defaults for a float32 array, and Open3D's stubs only
        # declare the ndarray overload with both (the one-argument call works at runtime but fails mypy).
        r = scene.compute_closest_points(o3d.core.Tensor(p, o3d.core.float32, o3d.core.Device("CPU:0")))
        d = p.astype(np.float64) - r["points"].numpy()
        n = normals[r["primitive_ids"].numpy()]
        lateral = np.linalg.norm(d - (d * n).sum(1, keepdims=True) * n, axis=1)
        out[i:i + 1_000_000] = lateral <= margin + NUMERIC_TOL
    return out


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


# --- The verdict stage (issue #40: moved from notebook 03a, no rule change) -------------------------------------------------------------------------------------------------

HOW_OWN: Final = 1  # how place_wall_points decided a point's side: its own free space,
HOW_PLANE: Final = 2  # its plane's side,
HOW_AMBIGUOUS: Final = 3  # neither (the nearest room-facing face decides)


@dataclass(frozen=True)
class VerdictRules:
    """The constants of the verdict rules, in metres. Judgement calls are marked (not from a standard); the defaults are the values 03a ran with."""

    tol: float = 0.015  # USIBD LOA30: at most 15 mm at 2 sigma (95 %)
    band: float = 0.10  # (judgement call) scan points further than this from every element surface are ignored
    min_points: int = 2000  # (judgement call) 1 cm voxels give one point per cm2, so 2000 points is about 0.2 m2 of scanned surface
    min_frac_ok: float = 0.95  # LOA30 is "specified at the 95 % confidence level": 15 mm is at 2 sigma, so 95 % of an element's points must lie within it
    min_frac_cluster: float = 0.8  # (judgement call) shifted: share of points within `tol` of the median; clutter and edges leave a real offset plane only 78 to 94 % near it, and 0.8 still rejects a 55/45 bimodal wall
    side_near: float = 0.03  # (judgement call) wall side test: look this far from a wall point along the thickness axis, beyond the point's own surface noise,
    side_far: float = 0.20  # to this far: past a 10 cm drywall's other face, short of most furniture, in
    side_step: float = 0.02  # steps of one occupancy voxel
    occ_voxel: float = 0.02  # (judgement call) occupancy grid voxel of the side test
    vote_bin: float = 0.005  # plane vote: 5 mm bins along the thickness axis; the window is `tol` each side (`vote_half` bins)
    vote_share: float | None = 0.5  # (judgement call) a plane takes the side that more than this share of its points show by themselves; None: no plane vote (03a's section 3 gives the reason)
    junction: float | None = 0.10  # (judgement call) a wall point within this of any other element's surface is at a junction and left out of the wall's verdict (03a's section 3: the reason, and the sensitivity at 0, 5, 10, 15 cm); None: no margin
    probe: float = 0.05  # (judgement call) a wall face is room-facing if the point this far outside it, along its normal, is within the room box's extent along that normal (half of a 10 cm wall)
    own_face: bool = True  # False: no own-face patch (issue #20)
    own_face_margin: float = 0.01  # (judgement call, tuned on held-out rooms) edge allowance in m of the own-face patch: 1 cm is the scan's voxel
    own_face_classes: tuple[str, ...] = ("IfcWallStandardCase", "IfcSlab", "IfcCovering")  # (judgement call, tuned) the classes with one or two broad faces
    own_face_one_sided: bool = True  # (judgement call, tuned) a wall is patched only if exactly one of its faces is room-facing: a partition is left as it was

    @property
    def vote_half(self) -> int:
        return round(self.tol / self.vote_bin)

    @property
    def reach(self) -> float:
        """How far from an element's bounding box a scan point can still matter: the band, the side test's far end and one occupancy voxel more."""
        return self.band + self.side_far + self.occ_voxel


RULES: Final = VerdictRules()


class Mesh(Protocol):
    @property
    def vertices(self) -> np.ndarray: ...
    @property
    def faces(self) -> np.ndarray: ...
    @property
    def ifc_class(self) -> str: ...


class Element(Mesh, Protocol):
    @property
    def global_id(self) -> str: ...


class Judgement(TypedDict):
    verdict: str
    reason: str
    point_count: int
    median_m: float
    spread_m: float
    share_within_tol: float
    cluster_share: float


class WallInfo(TypedDict):
    axis: int  # the thickness axis in plan
    sides: list[int]  # room-facing sides: 1 for a boundary wall, 2 for a partition inside the box
    ref: int  # reference side
    n_band: int
    n_dropped: int
    n_ambiguous: int
    n_side: dict[int, int]
    n_by_plane: int
    n_overruled: int


Occupancy = tuple[np.ndarray, np.ndarray]  # (lower corner of the lattice, boolean grid)


@dataclass
class SideTest:
    """What `measure` found out about the walls' sides, per point (arrays) or per wall (dicts keyed by element index)."""

    how: np.ndarray
    walls: dict[int, WallInfo]
    fallback: np.ndarray
    d_other: np.ndarray
    signed_side: np.ndarray
    occ: dict[int, Occupancy]


def _mesh_of(e: Mesh) -> o3d.geometry.TriangleMesh:
    m = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(e.vertices), o3d.utility.Vector3iVector(e.faces))
    m.compute_triangle_normals()
    return m


def _triangle_normals(e: Mesh) -> np.ndarray:
    # Open3D's own normals (not `_unit_normals`): the verdicts of 03a were made with them, and they are bit-identical to what 03a computed.
    return np.asarray(_mesh_of(e).triangle_normals)


def judge(s: np.ndarray, rules: VerdictRules = RULES) -> Judgement:
    """One element's verdict from its signed offsets `s` (metres, within the band). The element is judged on its whole patch, wherever it lies."""
    n = len(s)
    median = float(np.median(s)) if n else float("nan")
    spread = 1.4826 * float(np.median(np.abs(s - median))) if n else float("nan")  # robust sigma, informational only
    share = float(np.mean(np.abs(s) <= rules.tol)) if n else 0.0
    one_cluster = float(np.mean(np.abs(s - median) <= rules.tol)) if n else 0.0  # share of points within tol of the median
    if n == 0:
        verdict, reason = "not confirmed", "no points"
    elif n < rules.min_points:
        verdict, reason = "not confirmed", "too few points"
    elif share >= rules.min_frac_ok:
        verdict, reason = "OK", ""
    elif abs(median) > rules.tol and one_cluster >= rules.min_frac_cluster:
        verdict, reason = "shifted", ""
    else:
        verdict, reason = "not confirmed", "inconsistent offsets"
    return Judgement(verdict=verdict, reason=reason, point_count=n, median_m=median, spread_m=spread, share_within_tol=share, cluster_share=one_cluster)


def room_facing(e: Mesh, lo: np.ndarray, hi: np.ndarray, rules: VerdictRules = RULES) -> np.ndarray:
    """Boolean per triangle of a wall: vertical faces whose outward normal points into the box [lo, hi] (plan view). The box is taken along the
    normal only (its extent in that direction), because a wall runs on beyond the box and its triangles there still face the same way."""
    n = _triangle_normals(e)
    probe = e.vertices[e.faces].mean(1) + rules.probe * n
    a, b = n[:, :2] * lo[:2], n[:, :2] * hi[:2]
    s = (probe[:, :2] * n[:, :2]).sum(1)
    return (np.abs(n[:, 2]) < 0.5) & (s >= np.minimum(a, b).sum(1)) & (s <= np.maximum(a, b).sum(1))


def closest_signed(scene: o3d.t.geometry.RaycastingScene, normals: np.ndarray, first: np.ndarray, pts: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Nearest triangle of the scene to each point: its geometry id, the distance, and the offset along that triangle's normal.
    normals: all triangles' normals in geometry order; first[g]: index of geometry g's first triangle in it."""
    geom, dist, signed = np.empty(len(pts), np.int32), np.empty(len(pts), np.float32), np.empty(len(pts), np.float32)
    for i in range(0, len(pts), 500_000):
        p = np.ascontiguousarray(pts[i:i + 500_000], dtype=np.float32)
        r = scene.compute_closest_points(o3d.core.Tensor(p, o3d.core.float32, o3d.core.Device("CPU:0")))
        g, prim, foot = r["geometry_ids"].numpy(), r["primitive_ids"].numpy(), r["points"].numpy()
        geom[i:i + 500_000] = g
        dist[i:i + 500_000] = np.linalg.norm(p - foot, axis=1)
        signed[i:i + 500_000] = np.einsum("ij,ij->i", p - foot, normals[first[g] + prim])
    return geom, dist, signed


def occupancy(pts: np.ndarray, voxel: float) -> Occupancy:
    """Dense boolean grid over the points' bounding box: True where a voxel of side `voxel` holds at least one scan point. The lattice is anchored at multiples
    of `voxel` in the model frame (not at the points' minimum), so a voxel is occupied or not whatever the other points of the set are."""
    lo = np.floor(pts.min(0).astype(np.float64) / voxel) * voxel
    grid = np.zeros(np.ceil((pts.max(0) - lo) / voxel).astype(int) + 1, bool)
    j = np.floor((pts - lo) / voxel).astype(int)
    grid[j[:, 0], j[:, 1], j[:, 2]] = True
    return lo, grid


def occupied_along(occ: Occupancy, p: np.ndarray, axis: int, sign: int, rules: VerdictRules = RULES) -> np.ndarray:
    """Per point: is any voxel occupied from `side_near` to `side_far` away along sign * axis? Outside the grid counts as free."""
    lo, grid = occ
    hit = np.zeros(len(p), bool)
    for d in np.arange(rules.side_near, rules.side_far + 1e-9, rules.side_step):
        q = p.astype(np.float64)
        q[:, axis] += sign * d
        j = np.floor((q - lo) / rules.occ_voxel).astype(int)
        inside = ((j >= 0) & (j < grid.shape)).all(1)
        hit[inside] |= grid[j[inside, 0], j[inside, 1], j[inside, 2]]
    return hit


def plane_vote(u: np.ndarray, facing: np.ndarray, share: float, rules: VerdictRules = RULES) -> np.ndarray:
    """Per point: the side its surface plane shows as a whole, or 0. u: the points' coordinate along the wall's thickness axis; facing: what each
    point shows by itself (1, -1 or 0). A plane is the points within `tol` of u (`vote_half` bins of `vote_bin` each side); it takes a side if more than
    `share` of all its points show that side by themselves."""
    b = np.floor((u - u.min()) / rules.vote_bin).astype(int)
    window = np.ones(2 * rules.vote_half + 1)
    count = lambda m: np.convolve(np.bincount(b[m], minlength=max(b.max() + 1, window.size)), window, "same")[b]  # np.convolve "same" returns the longer input: pad to the window
    total, plus, minus = count(np.ones(len(u), bool)), count(facing == 1), count(facing == -1)
    return np.where(plus > share * total, 1, np.where(minus > share * total, -1, 0))


def place_wall_points(e: Mesh, face_set: np.ndarray, p: np.ndarray, fallback: np.ndarray, occ: Occupancy, rules: VerdictRules = RULES) -> tuple[np.ndarray, np.ndarray, WallInfo]:
    """The scan points p (assigned to wall e, within the band) -> their signed offsets along the reference side's normal, NaN for the points that are the
    back of the wall; `fallback` is the offset by the nearest room-facing face (the rule before the side test), used where the side is ambiguous.
    Returns the offsets, how each point was decided (HOW_OWN: free space on one side only, HOW_PLANE: its plane's side, HOW_AMBIGUOUS: fallback) and the counts.
    The plane vote takes its share from `rules.vote_share` (None: no vote)."""
    n = _triangle_normals(e)
    a = int(np.argmin(np.ptp(e.vertices[:, :2], axis=0)))  # the thickness axis in plan
    assert np.all(np.minimum(np.abs(n[face_set, 0]), np.abs(n[face_set, 1])) < 1e-3), "a wall is not aligned with the model axes"
    broad = {s: face_set & (n[:, a] * s > 0.99) for s in (1, -1)}  # the wall's two big faces (end faces left out), by the sign of their normal along the axis
    sides = [s for s in (1, -1) if broad[s].any()]  # room-facing sides: 1 for a boundary wall, 2 for a partition inside the box
    assert sides, "a wall has no room-facing side"
    free_plus, free_minus = ~occupied_along(occ, p, a, +1, rules), ~occupied_along(occ, p, a, -1, rules)
    own = np.where(free_plus & ~free_minus, 1, np.where(~free_plus & free_minus, -1, 0))  # the direction the surface was seen from; 0: ambiguous
    plane = plane_vote(p[:, a], own, rules.vote_share, rules) if rules.vote_share is not None else np.zeros(len(p), int)  # vote_share None: no plane vote
    facing = np.where(plane != 0, plane, own)  # a plane that most of its own points see from one side takes that side, also from the ones that say otherwise
    off: dict[int, np.ndarray] = {}  # per room-facing side: the offset to that side's faces, along its outward normal
    for s in sides:
        sub = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(e.vertices), o3d.utility.Vector3iVector(e.faces[broad[s]]))
        sub_scene = o3d.t.geometry.RaycastingScene()
        sub_scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(sub))
        _, d_face, s_face = closest_signed(sub_scene, n[broad[s]], np.zeros(1, int), p)
        off[s] = np.copysign(d_face, s_face)
    side = np.zeros(len(p), int)  # the room-facing side each point is measured against
    dropped = np.zeros(len(p), bool)  # seen from a side that is not room-facing: the neighbouring room's surface
    for s in (1, -1):
        if s in sides:
            side[facing == s] = s
        else:
            dropped |= facing == s
    ambiguous = facing == 0
    side[ambiguous] = np.where(np.abs(off[1][ambiguous]) <= np.abs(off[-1][ambiguous]), 1, -1) if len(sides) == 2 else sides[0]
    n_side = {s: int(((side == s) & ~dropped).sum()) for s in sides}
    ref = sides[0] if len(sides) == 1 else (1 if n_side[1] >= n_side[-1] else -1)  # reference side: the one with more points, ties to +axis
    sign = np.where(side == ref, 1.0, -1.0)  # the other side's offsets are flipped onto the reference normal
    signed = np.where(ambiguous, fallback, np.where(side == 1, off[1] if 1 in sides else 0, off[-1] if -1 in sides else 0)) * sign
    signed = signed.astype(np.float32)
    signed[dropped] = np.nan
    how = np.where(ambiguous, HOW_AMBIGUOUS, np.where(facing == own, HOW_OWN, HOW_PLANE)).astype(np.int8)
    info = WallInfo(axis=a, sides=sides, ref=ref, n_band=len(p), n_dropped=int(dropped.sum()), n_ambiguous=int(ambiguous.sum()), n_side=n_side,
                    n_by_plane=int((how == HOW_PLANE).sum()), n_overruled=int(((own != 0) & (facing != own)).sum()))
    return signed, how, info


def apply_junction(signed_side: np.ndarray, d_other: np.ndarray, junction: float | None) -> np.ndarray:
    """The one place where the junction margin is applied: the offsets with NaN where a point is within `junction` of another element's surface (d_other is NaN for
    points that are not a wall's, so they are never touched; junction None: no margin)."""
    s = signed_side.copy()
    if junction is not None:
        s[d_other <= junction] = np.nan
    return s


def measure(els: Sequence[Mesh], faces: Sequence[np.ndarray], pts: np.ndarray, rules: VerdictRules = RULES) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, SideTest]:
    """Returns per point: the element index, the distance to it, the signed offset, the offset by 00's nearest-triangle rule, and the wall side test's findings (a `SideTest`).
    els: the elements to judge first, then their neighbours (never judged: their faces are all True, which skips them below; they take the points that are nearer to them,
    and they are "another element" at a wall's junctions). faces[i]: boolean per triangle of element i, the triangles its offset is measured against (all True is 00's rule).
    A point is in element i's patch if i is its nearest element over all of `els` and the distance is <= `rules.band` (the caller selects).
    For a wall (not all True) the offset is along the reference side's normal, and NaN for a point that is the back of the wall, and for a point within
    `rules.junction` of any other element's surface (a junction with the ceiling, the floor, a window, another wall: not the wall's own plane; None: off).
    The SideTest also holds d_other (distance to the nearest other element, walls' points only), signed_side (the offsets before the margin, apply_junction's input)
    and occ (the side test's occupancy grid of each wall: the points within `rules.reach` of the wall's bounding box, so it does not depend on which points are passed)."""
    scene = o3d.t.geometry.RaycastingScene()
    normal_list: list[np.ndarray] = []
    first: list[int] = [0]
    t_meshes: list[o3d.t.geometry.TriangleMesh] = []
    for e in els:
        m = _mesh_of(e)
        normal_list.append(np.asarray(m.triangle_normals))
        t_meshes.append(o3d.t.geometry.TriangleMesh.from_legacy(m))
        scene.add_triangles(t_meshes[-1])  # geometry ids follow this order
        first.append(first[-1] + len(e.faces))
    geom, dist, nearest = closest_signed(scene, np.concatenate(normal_list), np.array(first), pts)
    signed_side = nearest.copy()  # walls' entries are replaced below by the side test's offsets
    how: np.ndarray = np.zeros(len(pts), np.int8)
    walls_info: dict[int, WallInfo] = {}
    occ: dict[int, Occupancy] = {}
    fallback_all = np.full(len(pts), np.nan, np.float32)
    d_other = np.full(len(pts), np.nan, np.float32)
    reach = rules.reach
    for i, keep in enumerate(faces):
        if keep.all():
            continue
        idx = np.flatnonzero((geom == i) & (dist <= rules.band))  # only the points that enter the comparison
        if len(idx) == 0:
            continue  # a wall with no scan point in its patch has nothing to measure (issue #31: occupancy and plane_vote take min of nothing); it has no entry in walls_info and judge reads 'no points'
        sub = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(els[i].vertices), o3d.utility.Vector3iVector(els[i].faces[keep]))
        sub_scene = o3d.t.geometry.RaycastingScene()
        sub_scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(sub))
        _, d_face, s_face = closest_signed(sub_scene, normal_list[i][keep], np.zeros(1, int), pts[idx])
        fallback = np.copysign(d_face, s_face)  # the sign along the normal, the size as the distance: a point past a face's edge (above the wall's top) is not at offset 0
        fallback_all[idx] = fallback
        lo_w, hi_w = els[i].vertices.min(0) - reach, els[i].vertices.max(0) + reach
        occ[i] = occupancy(pts[((pts >= lo_w) & (pts <= hi_w)).all(1)], rules.occ_voxel)  # this wall's grid; every lookup from a point of its patch falls inside it
        signed_side[idx], how[idx], walls_info[i] = place_wall_points(els[i], keep, pts[idx], fallback, occ[i], rules)
        if len(els) > 1:
            others = o3d.t.geometry.RaycastingScene()  # every element but this wall: the neighbours too
            for j in range(len(els)):
                if j != i:
                    others.add_triangles(t_meshes[j])
            d_other[idx] = others.compute_distance(o3d.core.Tensor(np.ascontiguousarray(pts[idx], dtype=np.float32), o3d.core.float32, o3d.core.Device("CPU:0"))).numpy()
    return geom, dist, apply_junction(signed_side, d_other, rules.junction), nearest, SideTest(how=how, walls=walls_info, fallback=fallback_all, d_other=d_other, signed_side=signed_side, occ=occ)


def own_face_triangles(e: Mesh, face_set: np.ndarray) -> np.ndarray:
    """The triangles that are the element's own face(s): a wall's room-facing broad faces (across its thickness axis), a slab's or covering's two broad faces (across z).
    A deep covering's side faces are not counted (#32): room B's 0.5 m Forros 1 is the only slab or covering deeper than 15 cm in room B and the held-out rooms, so no held-out room can check such a rule."""
    if e.ifc_class == "IfcWallStandardCase":
        return aligned_faces(e.vertices, e.faces, int(np.argmin(np.ptp(e.vertices[:, :2], axis=0))), among=face_set)
    return aligned_faces(e.vertices, e.faces, 2)


def past_edge_mask(els: Sequence[Mesh], face_sets: Sequence[np.ndarray], geom: np.ndarray, band: np.ndarray, walls: dict[int, WallInfo], pts: np.ndarray,
                   rules: VerdictRules = RULES) -> np.ndarray:
    """Per point: does it lie past the edge of the own face of the element it is assigned to (issue #20)? Only band points of an element in `rules.own_face_classes` can; a wall with two room-facing
    faces (a partition) is left alone with `rules.own_face_one_sided`. `walls` is the side test's per-wall info, `face_sets[i]` the triangles of element i that the room sees."""
    past = np.zeros(len(pts), bool)
    if not rules.own_face:
        return past
    for i, e in enumerate(els):
        idx = np.flatnonzero((geom == i) & band)
        if e.ifc_class not in rules.own_face_classes or len(idx) == 0 or (rules.own_face_one_sided and e.ifc_class == "IfcWallStandardCase" and len(walls[i]["sides"]) > 1):
            continue
        tri = own_face_triangles(e, face_sets[i])
        if tri.any():
            past[idx] = ~over_own_face(pts[idx], e.vertices, e.faces[tri], rules.own_face_margin)
    return past


def judged_faces(e: Mesh, lo: np.ndarray, hi: np.ndarray, rules: VerdictRules = RULES) -> np.ndarray:
    """The triangles an element's offset is measured against: a wall's room-facing faces (by the room box [lo, hi]), every triangle of any other class."""
    return room_facing(e, lo, hi, rules) if e.ifc_class == "IfcWallStandardCase" else np.ones(len(e.faces), bool)


@dataclass
class PatchView:
    """What `element_rows` reads from `Patches`."""

    signed: np.ndarray
    how: np.ndarray
    points_of: list[np.ndarray]
    dropped_of: list[np.ndarray]
    junction_of: list[np.ndarray]
    past_of: list[np.ndarray]
    walls: dict[int, WallInfo]


@dataclass
class Patches:
    """The scan points assigned to the elements, for the scope's elements (the first `n_scope` of the element list). Per point: the nearest element, the distance, the signed offset
    (NaN where a point does not count), the offset by 00's rule and the side test; masks over the points; and per scope element the indices of its counted points (`points_of`),
    of the points that are the back of a wall (`dropped_of`), at a junction (`junction_of`) and past the edge of its own face (`past_of`)."""

    geom_id: np.ndarray
    distance: np.ndarray
    signed: np.ndarray
    signed_nearest: np.ndarray
    side: SideTest
    band: np.ndarray
    back: np.ndarray
    at_junction: np.ndarray
    in_band: np.ndarray
    past_edge: np.ndarray
    n_scope: int
    points_of: list[np.ndarray]
    past_of: list[np.ndarray]
    dropped_of: list[np.ndarray]
    junction_of: list[np.ndarray]

    def view(self) -> PatchView:
        return PatchView(signed=self.signed, how=self.side.how, points_of=self.points_of, dropped_of=self.dropped_of, junction_of=self.junction_of, past_of=self.past_of, walls=self.side.walls)


def assign_patches(scope: Sequence[Element], others: Sequence[Element], points: np.ndarray, lo: np.ndarray, hi: np.ndarray, rules: VerdictRules = RULES) -> Patches:
    """Every scan point goes to the nearest element (the `scope`, which is judged, and `others`, the neighbours: never judged, they compete for points and are 'another element' at junctions).
    Signed offset: walls against their room-facing faces (by the room box [lo, hi]), on the side each point was seen from; the neighbours get all-True faces: no verdict, no side test.
    The scope comes first in the element list (index i < len(scope) is scope[i])."""
    scope_fc = [judged_faces(e, lo, hi, rules) for e in scope]
    geom, dist, sgn, nearest, side = measure([*scope, *others], scope_fc + [np.ones(len(e.faces), bool) for e in others], points, rules)
    n_scope = len(scope)
    bnd = dist <= rules.band
    past = past_edge_mask(scope, scope_fc, geom, bnd, side.walls, points, rules)  # band points past the edge of their element's own face (issue #20)
    mine = geom < n_scope  # the nearest element of the point is in scope; it is in that element's patch if it is also within the band
    bk = bnd & mine & np.isnan(side.signed_side)  # walls: the points seen from the neighbouring room
    jn = bnd & mine & ~np.isnan(side.signed_side) & np.isnan(sgn)  # walls: counted by the side test, but within the junction margin of another element
    ib = bnd & mine & ~np.isnan(sgn) & ~past  # the points that count: within the band, not the back of a wall, not at a junction, over the element's own face
    pe = bnd & mine & ~np.isnan(sgn) & past  # would count, but lie past the edge of their element's own face (issue #20)
    return Patches(geom_id=geom, distance=dist, signed=sgn, signed_nearest=nearest, side=side, band=bnd, back=bk, at_junction=jn, in_band=ib, past_edge=past, n_scope=n_scope,
                   points_of=[np.flatnonzero((geom == i) & ib) for i in range(n_scope)],
                   past_of=[np.flatnonzero((geom == i) & pe) for i in range(n_scope)],
                   dropped_of=[np.flatnonzero((geom == i) & bk) for i in range(n_scope)],
                   junction_of=[np.flatnonzero((geom == i) & jn) for i in range(n_scope)])


class VerdictRow(TypedDict):
    global_id: str
    ifc_class: str
    verdict: str
    point_count: int
    median_signed_offset_mm: float
    share_within_tol: float
    share_near_median: float
    spread_mm: float
    reason: str
    points_other_side: int  # walls: points seen from the neighbouring room and left out (0 for other classes)
    points_at_junction: int  # walls: points left out for lying within the junction margin of another element
    points_past_edge: int  # points left out for lying past the edge of the element's own face (any class)
    ambiguous_share: float | str  # walls: the share of the counted points whose side the scan could not tell ("" for other classes)
    reference_side: str  # walls: the outward normal that the offsets are expressed along ("" for other classes)
    room_facing_sides: int | str  # walls: 1 or 2 ("" for other classes)


def element_rows(scope: Sequence[Element], view: PatchView, use: np.ndarray, rules: VerdictRules = RULES) -> list[VerdictRow]:
    """One verdict row per element of `scope`. `use`: boolean mask over the points that enter the comparison (all True: no labels; the oracle's scan classes: with labels).
    For a wall, `points_other_side` counts the points (of those in `use`) that were seen from the neighbouring room and left out, `points_at_junction` those left out for lying within the
    junction margin of another element, `points_past_edge` those left out for lying past the edge of the element's own face (any class), `ambiguous_share` the share of the counted points
    whose side the scan could not tell, `reference_side` the outward normal that its offsets are expressed along (a wall with two room-facing sides: the one with more points)."""
    rows: list[VerdictRow] = []
    for i, e in enumerate(scope):
        idx = view.points_of[i]
        j = judge(view.signed[idx[use[idx]]].astype(np.float64), rules)
        w = view.walls.get(i)
        rows.append(VerdictRow(
            global_id=e.global_id, ifc_class=e.ifc_class, verdict=j["verdict"], point_count=j["point_count"], median_signed_offset_mm=j["median_m"] * 1000,
            share_within_tol=j["share_within_tol"], share_near_median=j["cluster_share"], spread_mm=j["spread_m"] * 1000, reason=j["reason"],
            points_other_side=int(use[view.dropped_of[i]].sum()) if w else 0, points_at_junction=int(use[view.junction_of[i]].sum()) if w else 0, points_past_edge=int(use[view.past_of[i]].sum()),
            ambiguous_share=float(np.mean(view.how[idx[use[idx]]] == HOW_AMBIGUOUS)) if w and j["point_count"] else (0.0 if w else ""),
            reference_side=(("+" if w["ref"] > 0 else "-") + "xy"[w["axis"]]) if w else "", room_facing_sides=len(w["sides"]) if w else ""))
    return rows


def judge_elements(scope: Sequence[Element], others: Sequence[Element], points: np.ndarray, use: np.ndarray, lo: np.ndarray, hi: np.ndarray, rules: VerdictRules = RULES) -> list[VerdictRow]:
    """The verdict of every element of `scope` from the scan `points` (model frame): one row each.

    `others` are the neighbouring elements (never judged: they take the points that are nearer to them and are 'another element' at a wall's junctions); [lo, hi] is the room box (it
    decides which faces of a wall are room-facing, not which points count); `use` is the mask of the points that enter the comparison (all True: without oracle labels).
    03a calls `assign_patches` once and `element_rows` per mask, because the assignment (`measure`) is the expensive step; this is the one-call form."""
    return element_rows(scope, assign_patches(scope, others, points, lo, hi, rules).view(), use, rules)

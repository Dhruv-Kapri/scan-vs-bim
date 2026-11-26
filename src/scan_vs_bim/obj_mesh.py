"""Read a PC2Model model OBJ with every quad and n-gon cut into triangles (#53): Open3D's OBJ reader drops them silently."""

import tempfile
from pathlib import Path

import mapbox_earcut
import numpy as np
import open3d as o3d
import shapely


def _newell_normal(points: np.ndarray) -> np.ndarray:
    """Normal of a (planar) polygon, length = twice its area; points the way the polygon winds (counter-clockwise seen from its tip)."""
    return np.cross(points, np.roll(points, -1, axis=0)).sum(axis=0)


def _is_convex(points: np.ndarray, normal: np.ndarray) -> bool:
    """Every consecutive turn bends the way the polygon winds (no reflex vertex); collinear points pass, within a tolerance relative to its size."""
    edges = np.roll(points, -1, axis=0) - points
    turns = np.cross(np.roll(edges, 1, axis=0), edges) @ (normal / np.linalg.norm(normal))
    return bool(np.all(turns >= -1e-6 * np.ptp(points, axis=0).max() ** 2))


def _fan_flips(points: np.ndarray, normal: np.ndarray) -> bool:
    """A fan triangle from the first vertex faces against the polygon's normal: a reflex turn below `_is_convex`'s tolerance, which the
    fan's long thin triangles would overlap across (house_11, #53)."""
    spokes = points[1:] - points[0]
    return bool(np.any(np.cross(spokes[:-1], spokes[1:]) @ normal < -1e-9 * float(normal @ normal)))


def _fan(n: int) -> list[tuple[int, int, int]]:
    """Triangles (0, i, i + 1) of an n-gon, as vertex positions in the polygon."""
    return [(0, i, i + 1) for i in range(1, n - 1)]


def _signed_area(xy: np.ndarray) -> float:
    """Shoelace area of a 2D ring: positive counter-clockwise."""
    return 0.5 * float(np.dot(xy[:, 0], np.roll(xy[:, 1], -1)) - np.dot(np.roll(xy[:, 0], -1), xy[:, 1]))


def _contains(ring: np.ndarray, point: np.ndarray) -> bool:
    """Even-odd test of a 2D point against a 2D ring."""
    x, y = point
    nxt = np.roll(ring, -1, axis=0)
    crossing = (ring[:, 1] > y) != (nxt[:, 1] > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        x_at = ring[:, 0] + (y - ring[:, 1]) * (nxt[:, 0] - ring[:, 0]) / (nxt[:, 1] - ring[:, 1])
    return bool(np.count_nonzero(crossing & (x < x_at)) % 2)


def _rings(points: np.ndarray) -> list[list[int]]:
    """Corner indices of the simple rings a face splits into at repeated vertex positions (exact equality): walk the corners on a stack,
    and when a position already on the stack recurs, the corners since it close a ring. A keyhole face (a hole joined to the outline by a bridge
    walked twice) or a pinched one becomes its outline and its holes. Rings with fewer than 3 corners are dropped."""
    keys = [tuple(p) for p in points]
    stack: list[int] = []
    rings: list[list[int]] = []
    for i, key in enumerate(keys):
        seen = next((k for k, j in enumerate(stack) if keys[j] == key), None)
        if seen is not None:
            rings.append(stack[seen:])
            del stack[seen:]
        stack.append(i)
    rings.append(stack)
    return [r for r in rings if len(r) >= 3]


def _project(points: np.ndarray, normal: np.ndarray) -> np.ndarray:
    """A face's corners in 2D coordinates (u, v) of its Newell plane; (u, v, normal) is right-handed, so the face runs counter-clockwise."""
    n_hat = normal / np.linalg.norm(normal)
    u = np.cross(n_hat, np.eye(3)[np.argmin(np.abs(n_hat))])
    u /= np.linalg.norm(u)
    return np.column_stack((points @ u, points @ np.cross(n_hat, u)))


def _earcut(xy: np.ndarray, rings: list[list[int]]) -> list[tuple[int, int, int]]:
    """Triangles of a concave face as corner indices, keeping its winding: `rings` (the face split at repeated vertices, `xy` its corners in its
    plane) are outlines when counter-clockwise and holes when clockwise, each hole goes to the smallest outline containing its vertex mean (a hole
    inside no outline is triangulated alone), and each outline with its holes is triangulated by earcut. Earcut returns counter-clockwise triangles
    whatever the input winding, which is the face's winding in the plane. Empty if earcut finds no triangle."""
    areas = {tuple(r): _signed_area(xy[r]) for r in rings}
    outlines = [r for r, a in areas.items() if a > 0]
    holes: dict[tuple[int, ...], list[tuple[int, ...]]] = {r: [] for r in outlines}
    groups: list[list[tuple[int, ...]]] = []
    for hole in (r for r, a in areas.items() if a < 0):
        inside = [o for o in outlines if _contains(xy[list(o)], xy[list(hole)].mean(axis=0))]
        if inside:
            holes[min(inside, key=areas.__getitem__)].append(hole)
        else:
            groups.append([hole])
    groups += [[o, *holes[o]] for o in outlines]
    triangles: list[tuple[int, int, int]] = []
    for group in groups:
        corners = [i for ring in group for i in ring]
        ends = np.cumsum([len(ring) for ring in group]).astype(np.uint32)
        found = mapbox_earcut.triangulate_float64(xy[corners], ends).reshape(-1, 3)
        triangles += [(corners[a], corners[b], corners[c]) for a, b, c in found]
    return triangles


def _crosses(xy: np.ndarray, rings: list[list[int]]) -> bool:
    """Some ring has two edges that cross each other (their interiors meet in a point). Rings touching themselves, or at repeated vertices,
    are not crossing; `LinearRing.is_simple` rules most rings out before the edge pairs are tested."""
    for ring in rings:
        ring_xy = xy[ring]
        if shapely.LinearRing(ring_xy).is_simple:
            continue
        edges = shapely.linestrings(np.stack((ring_xy, np.roll(ring_xy, -1, axis=0)), axis=1))
        if len(shapely.STRtree(edges).query(edges, predicate="crosses")[0]):
            return True
    return False


def _winding(xy: np.ndarray, x: float, y: float) -> int:
    """Winding number of the closed 2D polyline `xy` around the point (x, y): counter-clockwise turns count +1."""
    nxt = np.roll(xy, -1, axis=0)
    side = (nxt[:, 0] - xy[:, 0]) * (y - xy[:, 1]) - (x - xy[:, 0]) * (nxt[:, 1] - xy[:, 1])
    up = (xy[:, 1] <= y) & (y < nxt[:, 1]) & (side > 0)
    down = (nxt[:, 1] <= y) & (y < xy[:, 1]) & (side < 0)
    return int(np.count_nonzero(up) - np.count_nonzero(down))


def _cover(points: np.ndarray, xy: np.ndarray) -> tuple[list[tuple[int, int, int]], np.ndarray]:
    """Triangles of a face whose edges cross, covering the region it covers: all its edges are noded at their crossings, the cells they cut the plane
    into are kept when the face's outline winds around them (nonzero winding number, so a lobe wound backwards counts, a hole does not), and each
    cell is triangulated by earcut, counter-clockwise in the plane = along the face's Newell normal. A cell corner that is a corner of the face is that
    corner; any other (a crossing) becomes an extra point on the original 3D edge it lies on. Returns the triangles as indices into `points`, followed
    by the extra points (index len(points) + k = extra_points[k]), and the extra points as an array."""
    n = len(points)
    nxt = np.roll(np.arange(n), -1)
    moving = np.flatnonzero(np.any(xy != xy[nxt], axis=1))   # edges with a length
    noded = shapely.get_parts(shapely.unary_union(shapely.linestrings(np.stack((xy[moving], xy[nxt[moving]]), axis=1))))
    corner_of: dict[tuple[float, float], int] = {}
    for i in range(n - 1, -1, -1):
        corner_of[(float(xy[i, 0]), float(xy[i, 1]))] = i
    extra_xy: dict[tuple[float, float], int] = {}
    extra: list[np.ndarray] = []

    def index_of(x: float, y: float) -> int:
        if (x, y) in corner_of:
            return corner_of[(x, y)]
        if (x, y) not in extra_xy:
            a, b = xy[moving], xy[nxt[moving]]
            ab = b - a
            t = np.clip(((np.array([x, y]) - a) * ab).sum(axis=1) / (ab * ab).sum(axis=1), 0.0, 1.0)
            e = int(np.argmin(np.linalg.norm(a + t[:, None] * ab - [x, y], axis=1)))
            extra_xy[(x, y)] = len(extra)
            extra.append(points[moving[e]] + t[e] * (points[nxt[moving[e]]] - points[moving[e]]))
        return n + extra_xy[(x, y)]

    triangles: list[tuple[int, int, int]] = []
    for cell in shapely.get_parts(shapely.polygonize(noded)):
        if not _winding(xy, *cell.representative_point().coords[0]):
            continue
        rings = [np.asarray(cell.exterior.coords)[:-1], *(np.asarray(r.coords)[:-1] for r in cell.interiors)]
        corners = [index_of(float(x), float(y)) for ring in rings for x, y in ring]
        ends = np.cumsum([len(r) for r in rings]).astype(np.uint32)
        found = mapbox_earcut.triangulate_float64(np.concatenate(rings), ends).reshape(-1, 3)
        triangles += [(corners[a], corners[b], corners[c]) for a, b, c in found]
    return triangles, np.array(extra).reshape(-1, 3)


def _triangulate(points: np.ndarray) -> tuple[list[tuple[int, int, int]], np.ndarray]:
    """Fan for a convex polygon whose fan triangles all face its way (or one with no area); for a concave one, rings (outline + holes) split off at
    repeated vertices and triangulated with earcut, because a fan or a plain ear clip leaves the face, or overlaps, on these faces (#53). A concave face
    whose edges cross (a bowtie) is cut into the cells it covers instead (`_cover`). A face earcut gives no triangle for is fanned.
    Returns the triangles as indices into `points`, plus the extra points some triangles use (index len(points) + k = extra_points[k], shape (k, 3);
    empty unless the face's edges cross)."""
    normal = _newell_normal(points)
    no_extra = np.empty((0, 3))
    if np.linalg.norm(normal) == 0 or (_is_convex(points, normal) and not _fan_flips(points, normal)):
        return _fan(len(points)), no_extra
    xy, rings = _project(points, normal), _rings(points)
    if _crosses(xy, rings):
        covered = _cover(points, xy)
        if covered[0]:
            return covered
    return _earcut(xy, rings) or _fan(len(points)), no_extra


def _vertex_index(token: str, seen: int) -> int:
    """0-based vertex index of an OBJ face token (`v`, `v/vt`, `v//vn`, `v/vt/vn`; 1-based, negative = relative to the `seen` vertices read so far)."""
    index = int(token.split("/")[0])
    return index - 1 if index > 0 else seen + index


def load_model_mesh(obj: Path) -> o3d.geometry.TriangleMesh:
    """Read a model OBJ with every quad and n-gon cut into triangles: Open3D's reader (ASSIMP) silently drops non-triangle faces (#53).
    A convex face is fanned from its first vertex; a concave one is split at repeated vertices into rings (outline + holes) and triangulated with
    earcut, since a fan over it adds surface outside the face and a plain ear clip overlaps on faces that touch themselves; one whose edges cross
    is cut into the cells it covers, with the crossings as new vertices: `v` lines at the end of the file, so no index shifts, and the triangles
    using them are written with absolute `f a b c` indices (an OBJ face does not mix `v` and `v/vt/vn` tokens).
    A model of triangles only is read from the original file, unchanged; a relative `mtllib` is made absolute, as the cut OBJ is written to a temporary folder."""
    lines = obj.read_text().splitlines(keepends=True)
    out: list[str | tuple[str | int, ...]] = []   # a tuple is a triangle using extra vertices: str = absolute vertex index, int = extra vertex k
    vertices: list[list[float]] = []
    extra_vertices: list[np.ndarray] = []
    changed = False
    for line in lines:
        tokens = line.split()
        if len(tokens) > 3 and tokens[0] == "v":
            vertices.append([float(t) for t in tokens[1:4]])
        if len(tokens) > 4 and tokens[0] == "f":
            corners = tokens[1:]
            points = np.array([vertices[_vertex_index(t, len(vertices))] for t in corners])
            triangles, extra = _triangulate(points)
            absolute = [str(_vertex_index(t, len(vertices)) + 1) for t in corners]
            for tri in triangles:
                if max(tri) < len(corners):
                    out.append(f"f {corners[tri[0]]} {corners[tri[1]]} {corners[tri[2]]}\n")
                else:
                    out.append(tuple(absolute[i] if i < len(corners) else len(extra_vertices) + i - len(corners) for i in tri))
            extra_vertices += list(extra)
            changed = True
        elif tokens[:1] == ["mtllib"]:   # the temporary OBJ is elsewhere: point the library at the original's folder
            out.append(f"mtllib {obj.parent / line.split(None, 1)[1].strip()}\n" if len(tokens) > 1 else line)
        else:
            out.append(line)
    if not changed:
        return o3d.io.read_triangle_mesh(obj)
    n = len(vertices)
    text = [x if isinstance(x, str) else "f " + " ".join(t if isinstance(t, str) else str(n + 1 + t) for t in x) + "\n" for x in out]
    if extra_vertices and text and not text[-1].endswith("\n"):   # a last line without newline would run into the first new `v` line
        text[-1] += "\n"
    text += [f"v {x:.17g} {y:.17g} {z:.17g}\n" for x, y, z in extra_vertices]
    with tempfile.TemporaryDirectory() as tmp:   # not beside the original, which may be read-only
        triangulated = Path(tmp) / "triangulated.obj"
        triangulated.write_text("".join(text))
        return o3d.io.read_triangle_mesh(triangulated)


def non_triangle_share(obj: Path) -> float:
    """Share of an OBJ's faces that are not triangles: Open3D's reader drops them silently; `load_model_mesh` triangulates them (#53)."""
    n = other = 0
    with obj.open() as f:
        for line in f:
            if line.startswith("f "):
                n += 1
                other += len(line.split()) != 4
    return other / n if n else 0.0

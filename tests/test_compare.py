from collections.abc import Callable
from dataclasses import fields, is_dataclass, replace
from typing import Any, cast

import numpy as np
import open3d as o3d
import pytest

from scan_vs_bim.compare import RULES, VerdictRow, VerdictRules, aligned_faces, assign_patches, face_coverage, judge, judge_elements, mesh_of, over_own_face, own_face_triangles, plane_vote, recut
from scan_vs_bim.load import ElementMesh


def box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> tuple[np.ndarray, np.ndarray]:
    m = cast(o3d.geometry.TriangleMesh, o3d.geometry.TriangleMesh.create_box(x1 - x0, y1 - y0, z1 - z0).translate((x0, y0, z0)))
    return np.asarray(m.vertices), np.asarray(m.triangles)


def room_face_of_wall(v: np.ndarray, f: np.ndarray, y: float) -> np.ndarray:
    """The triangles of the wall's face at y = `y` (the face the room sees)."""
    tri = v[f]
    return np.flatnonzero(np.isclose(tri[:, :, 1], y).all(1))


# A wall along x: x 0 to 4, y 0 to 0.1, z 0 to 3. The room is on the +y side, so its own face is y = 0.1 (x 0..4, z 0..3).
V, F = box(0, 4, 0, 0.1, 0, 3)
OWN = F[room_face_of_wall(V, F, 0.1)]


def pts(*rows: list[float]) -> np.ndarray:
    return np.array(rows, float)


def test_points_over_the_face_are_kept_whatever_their_distance_in_front() -> None:
    p = pts([2, 0.1, 1.5], [2, 0.15, 1.5], [0.5, 0.2, 0.3], [3.9, 0.1, 2.9], [2, 0.0, 1.5])
    assert over_own_face(p, V, OWN).all()  # the last one is behind the face; still over it


# At an L-junction the neighbouring wall's face lies on the line where this face ends, so its points are over this face by projection; the junction margin elsewhere, not this predicate, leaves them out.
@pytest.mark.parametrize(
    ("point", "expected"),
    [
        pytest.param([4.0, 0.1, 1.5], True, id="on the end edge"),
        pytest.param([0.0, 0.1, 3.0], True, id="on a corner"),
        pytest.param([4.03, 0.1, 1.5], False, id="3 cm past the x=4 end"),
        pytest.param([4.09, 0.12, 1.5], False, id="9 cm past the end, in front"),
        pytest.param([-0.05, 0.1, 1.5], False, id="past the x=0 end"),
        pytest.param([2, 0.1, 3.04], False, id="past the top edge"),
        pytest.param([2, 0.12, 3.09], False, id="past the top edge, in front"),
        pytest.param([2, 0.1, -0.05], False, id="below the bottom edge"),
        pytest.param([4.0, 2.0, 1.5], True, id="L-junction: neighbour's face on the end line"),
    ],
)
def test_a_point_is_over_the_face_up_to_its_edges_and_not_past_them(point: list[float], expected: bool) -> None:
    assert over_own_face(pts(point), V, OWN, margin=0.0).tolist() == [expected]


def test_a_point_just_beyond_an_edge_is_kept_within_the_allowance_and_dropped_beyond_it() -> None:
    p = pts([4.008, 0.1, 1.5], [4.03, 0.1, 1.5])
    assert over_own_face(p, V, OWN, margin=0.01).tolist() == [True, False]
    assert over_own_face(p, V, OWN, margin=0.0).tolist() == [False, False]
    assert over_own_face(p, V, OWN, margin=0.05).tolist() == [True, True]


def test_a_partition_with_two_faces_counts_points_over_either() -> None:
    own = F[np.concatenate([room_face_of_wall(V, F, 0.1), room_face_of_wall(V, F, 0.0)])]
    p = pts([2, 0.0, 1.5], [2, 0.1, 1.5], [2, -0.2, 1.5], [4.05, 0.0, 1.5])
    assert over_own_face(p, V, own).tolist() == [True, True, True, False]


def test_an_empty_input_gives_an_empty_mask() -> None:
    assert over_own_face(np.zeros((0, 3)), V, OWN).shape == (0,)


def test_a_slab_is_judged_on_its_broad_faces_not_its_edge_faces() -> None:
    # A slab x 0..6, y 0..5, z 0..0.15. Its broad faces are z = 0 and z = 0.15. A point 2 cm beyond its x = 6 end is over its edge face (the side) but not over a broad face.
    v, f = box(0, 6, 0, 5, 0, 0.15)
    broad = f[aligned_faces(v, f, axis=2)]
    p = pts([3, 2, 0.15], [3, 2, 0.3], [6.02, 2, 0.15], [3, 5.2, 0.15])
    assert over_own_face(p, v, broad).tolist() == [True, True, False, False]
    assert over_own_face(p, v, f).tolist() == [True, True, True, True]  # with every triangle the edge faces pull the point in: why the broad faces are chosen


def test_aligned_faces_picks_triangles_whose_normal_is_along_the_axis() -> None:
    v, f = box(0, 4, 0, 0.1, 0, 3)
    m = aligned_faces(v, f, axis=1)
    assert set(np.flatnonzero(m)) == set(room_face_of_wall(v, f, 0.1)) | set(room_face_of_wall(v, f, 0.0))  # the y = 0 and y = 0.1 faces, two triangles each
    only = aligned_faces(v, f, axis=1, among=np.isin(np.arange(len(f)), np.flatnonzero(m)[:2]))
    assert np.flatnonzero(only).tolist() == np.flatnonzero(m)[:2].tolist()


def test_over_own_face_with_no_faces_keeps_no_point() -> None:
    # An element with no selected face has nothing to be over; no closest-point lookup on an empty scene.
    pts = np.array([[0.0, 0.0, 0.0], [1.0, 2.0, 3.0]])
    assert not over_own_face(pts, np.zeros((0, 3)), np.zeros((0, 3), int)).any()


def sample_face(x0: float, x1: float, z0: float, z1: float, y: float = 0.1, step: float = 0.01) -> np.ndarray:
    """Points on the plane y = `y`, one every `step` metres over x `x0`..`x1`, z `z0`..`z1` (offset by half a step so none sits on a cell border)."""
    x, z = np.meshgrid(np.arange(x0 + step / 2, x1, step), np.arange(z0 + step / 2, z1, step))
    return np.column_stack([x.ravel(), np.full(x.size, y), z.ravel()])


def test_a_fully_sampled_face_is_covered_and_half_the_points_cover_half() -> None:
    assert face_coverage(sample_face(0, 4, 0, 3), V, OWN, axis=1, cell=0.05) == pytest.approx(1.0)
    assert face_coverage(sample_face(0, 2, 0, 3), V, OWN, axis=1, cell=0.05) == pytest.approx(0.5)


def test_points_beyond_the_faces_edge_do_not_count() -> None:
    assert face_coverage(sample_face(4.1, 5, 0, 3), V, OWN, axis=1, cell=0.05) == 0.0
    assert face_coverage(np.vstack([sample_face(0, 4, 0, 3), sample_face(4.1, 5, 0, 3)]), V, OWN, axis=1, cell=0.05) == pytest.approx(1.0)


def test_a_partitions_two_faces_are_one_surface_not_two() -> None:
    both = F[aligned_faces(V, F, axis=1)]  # y = 0 and y = 0.1: both project onto the same rectangle
    assert face_coverage(sample_face(0, 4, 0, 3), V, both, axis=1, cell=0.05) == pytest.approx(1.0)


def test_a_triangle_seen_edge_on_covers_nothing() -> None:
    ends = F[aligned_faces(V, F, axis=0)]  # the wall's end faces, seen along y: lines, not areas
    assert face_coverage(sample_face(0, 4, 0, 3), V, ends, axis=1, cell=0.05) == 0.0


def test_no_points_cover_nothing() -> None:
    assert face_coverage(np.zeros((0, 3)), V, OWN, axis=1, cell=0.05) == 0.0


# --- judge_elements (#40): the verdict rules on synthetic known answers (ported from notebook 03a) ---------------------------------------------------------------------
# A 10 cm wall (x 0 to 0.1, y 0 to 5, z 0 to 3). The room box cuts it off at y = 0.5 and 4.9. With lo.x = -0.01 only the +x face (x = 0.1) is room-facing (a boundary wall);
# with lo.x = -1 both faces are (a partition inside the box).
BOUNDARY_BOX: tuple[np.ndarray, np.ndarray] = (np.array([-0.01, 0.5, 0.0]), np.array([4.0, 4.9, 3.0]))
PARTITION_BOX: tuple[np.ndarray, np.ndarray] = (np.array([-1.0, 0.5, 0.0]), np.array([4.0, 4.9, 3.0]))


def element(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float, ifc_class: str = "IfcWallStandardCase", global_id: str = "e") -> ElementMesh:
    v, f = box(x0, x1, y0, y1, z0, z1)
    return ElementMesh(global_id=global_id, ifc_class=ifc_class, vertices=v, faces=f)


def scan_plane(rng: np.random.Generator, x: float, y0: float = 0.6, y1: float = 4.4, z0: float = 0.3, z1: float = 2.7, noise: float = 0.003) -> np.ndarray:
    """A scanned plane at x = `x`: points on a 1 cm grid in y and z, `noise` metres of noise along x."""
    yy, zz = np.meshgrid(np.arange(y0, y1, 0.01), np.arange(z0, z1, 0.01))
    return np.column_stack([x + rng.normal(0, noise, yy.size), yy.ravel(), zz.ravel()]).astype(np.float32)


def judge_first(scope: list[ElementMesh], others: list[ElementMesh], planes: list[np.ndarray], room: tuple[np.ndarray, np.ndarray], rules: VerdictRules = RULES) -> VerdictRow:
    """The row of scope[0] from judge_elements on the concatenated scan planes, every point used (no labels)."""
    points = np.concatenate(planes)
    return judge_elements(scope, others, points, np.ones(len(points), bool), room[0], room[1], rules)[0]


@pytest.mark.parametrize(
    ("offsets", "verdict", "reason"),
    [
        pytest.param(lambda r: r.normal(0.03, 0.003, 5000), "shifted", "", id="a plane 3 cm off"),
        pytest.param(lambda r: r.normal(0.0, 0.003, 5000), "OK", "", id="a good plane"),
        pytest.param(lambda r: r.normal(0.03, 0.003, 50), "not confirmed", "too few points", id="50 points"),
        pytest.param(lambda r: np.array([]), "not confirmed", "no points", id="no points"),
        pytest.param(lambda r: r.uniform(-0.05, 0.05, 5000), "not confirmed", "inconsistent offsets", id="scattered offsets"),
        pytest.param(lambda r: np.concatenate([r.normal(0.04, 0.003, 2750), r.normal(0.0, 0.003, 2250)]), "not confirmed", "inconsistent offsets", id="two surfaces, 55 % / 45 %: not shifted"),
    ],
)
def test_judge_reads_the_rules_on_synthetic_offsets(offsets: Callable[[np.random.Generator], np.ndarray], verdict: str, reason: str) -> None:
    j = judge(offsets(np.random.default_rng(0)))
    assert (j["verdict"], j["reason"]) == (verdict, reason)


# 13 mm is inside LOA30's 15 mm and 17 mm outside it. With 0.5 mm of noise the margin is 4 sigma either way, so the verdict is not a matter of the draw. -17 mm puts the scanned plane inside the wall body.
@pytest.mark.parametrize(("offset", "verdict"), [(0.013, "OK"), (0.017, "shifted"), (-0.017, "shifted")])
def test_a_wall_on_the_loa30_boundary_reads_ok_or_shifted_at_the_offset(offset: float, verdict: str) -> None:
    row = judge_first([element(0, 0.1, 0, 5, 0, 3)], [], [scan_plane(np.random.default_rng(0), 0.1 + offset, noise=0.0005)], BOUNDARY_BOX)
    assert row["verdict"] == verdict
    assert abs(row["median_signed_offset_mm"] - offset * 1000) < 1


def test_a_wall_scanned_from_both_sides_keeps_only_its_room_facing_points() -> None:
    rng = np.random.default_rng(0)
    room_face, back = scan_plane(rng, 0.1), scan_plane(rng, 0.0)  # the neighbouring room's surface lies on the wall's back face
    row = judge_first([element(0, 0.1, 0, 5, 0, 3)], [], [room_face, back], BOUNDARY_BOX)
    assert (row["verdict"], row["point_count"], row["points_other_side"]) == ("OK", len(room_face), len(back))
    assert row["reference_side"] == "+x" and row["room_facing_sides"] == 1


def test_a_wall_scanned_only_on_its_back_face_is_shifted_by_the_wall_thickness() -> None:
    row = judge_first([element(0, 0.1, 0, 5, 0, 3)], [], [scan_plane(np.random.default_rng(0), 0.0)], BOUNDARY_BOX)
    assert row["verdict"] == "shifted" and abs(row["median_signed_offset_mm"] + 100) < 3


@pytest.mark.parametrize(("shift", "verdict"), [(0.03, "shifted"), (0.01, "OK")])
def test_a_partition_is_judged_on_whichever_face_the_scan_shows(shift: float, verdict: str) -> None:
    rng = np.random.default_rng(0)
    row = judge_first([element(shift, 0.1 + shift, 0, 5, 0, 3)], [], [scan_plane(rng, 0.1), scan_plane(rng, 0.0)], PARTITION_BOX)  # the scan has both faces where the wall really is; the model is `shift` off
    assert row["verdict"] == verdict
    assert row["room_facing_sides"] == 2
    if verdict == "shifted":
        assert abs(abs(row["median_signed_offset_mm"]) - shift * 1000) < 3 and row["share_near_median"] >= 0.95


# The wall (x 0..0.1, y 0..4.5) meets a ceiling slab above it, a floor slab below it and a second wall at its end. Strips 2.5 cm in front of the wall's plane in those corners (a fillet, a skirting, a cornice)
# are nearer to the wall than to the neighbour, but lie within 10 cm of it: the junction margin leaves them out.
CORNER_WALL: ElementMesh = element(0, 0.1, 0, 4.5, 0, 3.0)
CORNER_NEIGHBOURS: list[ElementMesh] = [element(-0.5, 4.1, -0.5, 4.6, 3.0, 3.2, "IfcSlab", "ceiling"), element(-0.5, 4.1, -0.5, 4.6, -0.2, 0.0, "IfcSlab", "floor"), element(0.1, 4.1, 4.5, 4.6, 0, 3.0, global_id="end wall")]


@pytest.mark.parametrize(
    ("plane_x", "strip_x", "verdict", "median_mm"),
    [pytest.param(0.1, 0.125, "OK", 0, id="clean plane, strips in front of it: OK"), pytest.param(0.13, 0.1, "shifted", 30, id="plane 3 cm in, strips on the model: the margin must not turn it OK")],
)
def test_the_junction_margin_leaves_corner_strips_out_and_judges_the_plane(plane_x: float, strip_x: float, verdict: str, median_mm: float) -> None:
    rng = np.random.default_rng(0)
    planes = [scan_plane(rng, plane_x), scan_plane(rng, strip_x, 0.6, 4.4, 2.9, 2.975), scan_plane(rng, strip_x, 0.6, 4.4, 0.025, 0.1), scan_plane(rng, strip_x, 4.4, 4.475, 0.3, 2.7)]
    row = judge_first([CORNER_WALL], CORNER_NEIGHBOURS, planes, BOUNDARY_BOX)
    assert row["verdict"] == verdict and abs(row["median_signed_offset_mm"] - median_mm) < 3
    assert row["points_at_junction"] > 0
    assert judge_first([CORNER_WALL], CORNER_NEIGHBOURS, planes, BOUNDARY_BOX, replace(RULES, junction=None))["points_at_junction"] == 0


# n1: the only scan is the neighbour's face, 2.9 m from the wall: no point within the side test's reach of the wall. n2: the neighbour's face is 25 cm in front of the wall: points within reach, none within the band.
@pytest.mark.parametrize("nx", [pytest.param(3.0, id="n1 neighbour out of reach"), pytest.param(0.35, id="n2 points in reach, none in the band")])
def test_a_wall_with_no_point_in_its_patch_reads_no_points(nx: float) -> None:
    neighbour = element(nx, nx + 0.1, 0.5, 2.0, 0.0, 3.0, global_id="neighbour")
    row = judge_first([element(0, 0.1, 0, 5, 0, 3)], [neighbour], [scan_plane(np.random.default_rng(0), nx, y1=1.9)], BOUNDARY_BOX)
    assert (row["verdict"], row["reason"], row["point_count"]) == ("not confirmed", "no points", 0)


def test_the_own_face_patch_leaves_out_a_surface_carried_past_the_walls_end() -> None:
    # The wall ends at y = 5. The scan has its face to y = 4.9 and then the surface beyond (y 5.02 to 5.11, 2 to 11 cm past the end: nearer to the end edge than BAND). Counted as the wall's, it would read as an offset.
    rng = np.random.default_rng(0)
    planes = [scan_plane(rng, 0.1, 4.3, 4.9), scan_plane(rng, 0.1, 5.02, 5.11)]
    wall = element(0, 0.1, 0, 5, 0, 3)
    with_patch, without = judge_first([wall], [], planes, BOUNDARY_BOX), judge_first([wall], [], planes, BOUNDARY_BOX, replace(RULES, own_face=False))
    assert without["verdict"] != "OK"
    assert with_patch["verdict"] == "OK" and abs(with_patch["median_signed_offset_mm"]) < 3 and with_patch["points_past_edge"] > 0


def test_plane_vote_does_not_let_two_of_ten_points_decide_a_narrow_walls_side() -> None:
    # All points in two 5 mm bins (less than the vote window); 2 of the 10 show a side by themselves.
    assert not plane_vote(np.array([0.0] * 2 + [0.006] * 8), np.array([1] * 2 + [0] * 8), 0.5).any()


def test_the_use_mask_decides_which_points_count_and_which_are_reported_left_out() -> None:
    # With oracle labels only the labelled points enter: a back plane outside the mask is neither counted nor reported as the other side.
    rng = np.random.default_rng(0)
    room_face, back = scan_plane(rng, 0.1), scan_plane(rng, 0.0)
    points = np.concatenate([room_face, back])
    use = np.arange(len(points)) < len(room_face) // 2  # half of the room face only
    row = judge_elements([element(0, 0.1, 0, 5, 0, 3)], [], points, use, *BOUNDARY_BOX)[0]
    assert (row["verdict"], row["point_count"], row["points_other_side"]) == ("OK", len(room_face) // 2, 0)


def test_the_tolerance_is_the_usibd_loa30_bound_not_a_tuning_value() -> None:
    assert RULES.tol == 0.015  # USIBD LOA30: at most 15 mm at 2 sigma


def test_a_door_like_element_is_taken_across_its_thinnest_plan_axis_not_z() -> None:
    # A door leaf x 0..0.05, y 0..0.9, z 0..2.1: its own faces are the two broad ones at x = 0 and x = 0.05, not its top and bottom (which the z fallback would give).
    door = element(0, 0.05, 0, 0.9, 0, 2.1, "IfcDoor")
    tri = own_face_triangles(door, np.ones(len(door.faces), bool))
    assert tri.sum() == 4
    x = door.vertices[door.faces[tri]][:, :, 0]
    assert np.isclose(x, x[:, :1]).all()  # each selected triangle lies in a plane x = const


def assert_same(a: Any, b: Any, path: str = "patches") -> None:
    """Field-by-field equality of two `Patches`, whatever they nest: arrays (NaN equal), lists, dicts, dataclasses."""
    if isinstance(a, np.ndarray):
        np.testing.assert_array_equal(a, b, err_msg=path)
    elif is_dataclass(a):
        for f in fields(a):
            assert_same(getattr(a, f.name), getattr(b, f.name), f"{path}.{f.name}")
    elif isinstance(a, dict):
        assert a.keys() == b.keys(), path
        for k in a:
            assert_same(a[k], b[k], f"{path}[{k}]")
    elif isinstance(a, (list, tuple)):
        assert len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b)):
            assert_same(x, y, f"{path}[{i}]")
    else:
        assert a == b, path


# The own-face cut is the only part of the assignment that `recut` redoes; the measurement under it (`measure`) is reused. A wall whose scan carries on past its end (the case above), and a partition,
# which `own_face_one_sided` leaves alone, are where the cut matters.
@pytest.mark.parametrize(
    ("room", "measured_with", "recut_to"),
    [
        pytest.param(BOUNDARY_BOX, replace(RULES, own_face=False), RULES, id="off to on"),
        pytest.param(BOUNDARY_BOX, RULES, replace(RULES, own_face=False), id="on to off"),
        pytest.param(PARTITION_BOX, RULES, replace(RULES, own_face_one_sided=False), id="partition: one-sided to all walls"),
        pytest.param(BOUNDARY_BOX, RULES, replace(RULES, own_face_margin=0.1), id="wider margin"),
    ],
)
def test_recut_gives_what_assign_patches_gives_from_the_same_measurement(room: tuple[np.ndarray, np.ndarray], measured_with: VerdictRules, recut_to: VerdictRules) -> None:
    rng = np.random.default_rng(0)
    points = np.concatenate([scan_plane(rng, 0.1, 4.3, 4.9), scan_plane(rng, 0.1, 5.02, 5.11)])
    scope = [element(0, 0.1, 0, 5, 0, 3)]
    measured = assign_patches(scope, [], points, *room, measured_with)
    expected = assign_patches(scope, [], points, *room, recut_to)
    assert not np.array_equal(measured.past_edge, expected.past_edge)  # the cut matters here, or this would pass on a recut that does nothing
    assert_same(recut(measured, scope, points, *room, recut_to), expected)


def test_assign_patches_refuses_an_element_in_both_scope_and_others() -> None:
    # It would compete with itself, and its back face would read as a junction at distance 0.
    wall = element(0, 0.1, 0, 5, 0, 3)
    with pytest.raises(AssertionError, match="global_id"):
        assign_patches([wall], [wall], scan_plane(np.random.default_rng(0), 0.1), *BOUNDARY_BOX)


def test_mesh_of_flip_negates_triangle_normals() -> None:
    """`flip=True` reverses every triangle's winding, so each normal is the negation of the unflipped one."""
    el = ElementMesh(global_id="g", ifc_class="IfcWall", vertices=V, faces=F)
    plain = np.asarray(mesh_of(el).triangle_normals)
    flipped = np.asarray(mesh_of(el, flip=True).triangle_normals)
    assert np.abs(plain).sum() > 0
    np.testing.assert_allclose(flipped, -plain)

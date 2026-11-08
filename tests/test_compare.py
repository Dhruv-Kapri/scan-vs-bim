from typing import cast

import numpy as np
import open3d as o3d
import pytest

from scan_vs_bim.compare import aligned_faces, face_coverage, over_own_face


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


def test_points_past_the_end_of_the_wall_are_not_over_its_face() -> None:
    p = pts([4.03, 0.1, 1.5], [4.09, 0.12, 1.5], [-0.05, 0.1, 1.5])  # past the x = 4 end (3 and 9 cm), and past the x = 0 end
    assert not over_own_face(p, V, OWN).any()


def test_points_past_the_top_and_bottom_edge_are_not_over_the_face() -> None:
    p = pts([2, 0.1, 3.04], [2, 0.12, 3.09], [2, 0.1, -0.05])
    assert not over_own_face(p, V, OWN).any()


def test_a_point_just_beyond_an_edge_is_kept_within_the_allowance_and_dropped_beyond_it() -> None:
    p = pts([4.008, 0.1, 1.5], [4.03, 0.1, 1.5])
    assert over_own_face(p, V, OWN, margin=0.01).tolist() == [True, False]
    assert over_own_face(p, V, OWN, margin=0.0).tolist() == [False, False]
    assert over_own_face(p, V, OWN, margin=0.05).tolist() == [True, True]


def test_the_edge_itself_is_over_the_face() -> None:
    assert over_own_face(pts([4.0, 0.1, 1.5], [0.0, 0.1, 3.0]), V, OWN).all()


def test_an_l_junction_points_past_the_end_of_the_wall_belong_to_the_neighbour() -> None:
    # A second wall B (x 4 to 4.1, y 0 to 3) closes the corner: its room face is x = 4 and the wall A ends there. A's own face is y = 0.1, x 0..4.
    # Points on B's face (x = 4) lie on the line where A's face ends, so they are over A's face by projection (the junction margin, not this predicate, leaves them out);
    # points on B's far side (x = 4.1 and beyond) are past A's end and are not over A's face.
    p = pts([4.0, 0.5, 1.5], [4.0, 2.0, 1.5], [4.1, 0.5, 1.5], [4.2, 0.1, 1.5])
    assert over_own_face(p, V, OWN).tolist() == [True, True, False, False]


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
    assert m.sum() == 4  # two triangles on each of the y = 0 and y = 0.1 faces
    assert np.allclose(np.abs(np.asarray(o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(v), o3d.utility.Vector3iVector(f[m])).compute_triangle_normals().triangle_normals)[:, 1]), 1)
    only = aligned_faces(v, f, axis=1, among=np.isin(np.arange(len(f)), np.flatnonzero(m)[:2]))
    assert only.sum() == 2


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

from pathlib import Path

import numpy as np
import open3d as o3d
import pytest

from scan_vs_bim.obj_mesh import load_model_mesh, non_triangle_share


def test_load_model_mesh_keeps_the_area_of_quads_and_ngons(tmp_path: Path) -> None:
    """Open3D's reader drops every non-triangle face (#53); the loader cuts them into triangles, whatever the token form."""
    obj = tmp_path / "model_m.obj"
    obj.write_text(
        "mtllib m.mtl\n"
        "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\n"             # unit quad: area 1
        "v 3 0 0\nv 4 0 0\nv 5 1 0\nv 4 2 0\nv 3 1 0\n"     # convex pentagon (area by the shoelace formula below)
        "v 6 0 0\nv 8 0 0\nv 6 2 0\n"                         # triangle: area 2
        "vt 0 0\nvn 0 0 1\n"
        "usemtl a\n"
        "f 1/1/1 2/1/1 3/1/1 4/1/1\n"
        "f 5 6 7 8 9\n"
        "f -3 -2 -1\n"
        "f 1//1 2//1 3//1 4//1\n"                              # the quad again, v//vn tokens: area 1
    )
    mesh = load_model_mesh(obj)
    pentagon = 0.5 * abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in
                             zip([(3, 0), (4, 0), (5, 1), (4, 2), (3, 1)], [(4, 0), (5, 1), (4, 2), (3, 1), (3, 0)])))
    assert len(mesh.triangles) == 2 + 3 + 1 + 2
    assert mesh.get_surface_area() == pytest.approx(1 + pentagon + 2 + 1)
    assert [p.name for p in tmp_path.iterdir()] == ["model_m.obj"]   # the temporary OBJ is gone


def test_load_model_mesh_loads_a_model_from_a_read_only_directory(tmp_path: Path) -> None:
    """The cut mesh is read from a temporary OBJ; it must not need to be written beside the original."""
    obj = tmp_path / "model_r.obj"
    obj.write_text("v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf 1 2 3 4\n")
    tmp_path.chmod(0o555)
    try:
        assert len(load_model_mesh(obj).triangles) == 2
    finally:
        tmp_path.chmod(0o755)


def test_load_model_mesh_of_a_triangle_only_model_is_what_open3d_reads(tmp_path: Path) -> None:
    obj = tmp_path / "model_t.obj"
    obj.write_text("v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 1\nf 1 2 3\nf 1/1 3/2 4/3\n")
    mesh, plain = load_model_mesh(obj), o3d.io.read_triangle_mesh(obj)
    assert np.array_equal(np.asarray(mesh.vertices), np.asarray(plain.vertices))
    assert np.array_equal(np.asarray(mesh.triangles), np.asarray(plain.triangles))


def test_load_model_mesh_loads_a_model_of_quads_only(tmp_path: Path) -> None:
    """veh_008's case: no triangle at all, so Open3D alone returns an empty mesh."""
    obj = tmp_path / "model_q.obj"
    obj.write_text("v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf 1 2 3 4\n")
    assert len(load_model_mesh(obj).triangles) == 2


def _rotation(angle: float, axis: tuple[float, float, float]) -> np.ndarray:
    """Rodrigues' rotation matrix about a unit-length-normalised axis."""
    k = np.asarray(axis, dtype=float)
    k /= np.linalg.norm(k)
    cross = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(angle) * cross + (1 - np.cos(angle)) * cross @ cross


@pytest.mark.parametrize("tilted", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_load_model_mesh_triangulates_a_concave_ngon_without_leaving_its_face(tmp_path: Path, tilted: bool, reverse: bool) -> None:
    """An L-shape (area 3) listed from a reflex-side vertex: a fan from (2,1) has area 4, 1 of it outside the face (#53). Tilted, so the projection is exercised;
    reversed, so the winding follows the face's own order."""
    corners = [(2, 1), (1, 1), (1, 2), (0, 2), (0, 0), (2, 0)]
    if reverse:
        corners.reverse()
    points = np.array([(x, y, 0.0) for x, y in corners])
    if tilted:
        points = points @ _rotation(0.7, (1, 2, 3)).T + np.array([5.0, -2.0, 1.0])
    newell = sum(np.cross(a, b) for a, b in zip(points, np.roll(points, -1, axis=0)))
    obj = tmp_path / "model_l.obj"
    obj.write_text("".join(f"v {x:.9f} {y:.9f} {z:.9f}\n" for x, y, z in points) + "f 1 2 3 4 5 6\n")
    mesh = load_model_mesh(obj)
    mesh.compute_triangle_normals()
    assert len(mesh.triangles) == 4
    assert mesh.get_surface_area() == pytest.approx(3)
    assert np.all(np.asarray(mesh.triangle_normals) @ newell > 0)


def test_load_model_mesh_fans_a_convex_ngon_exactly_as_before(tmp_path: Path) -> None:
    """Convex n-gons keep the plain fan from the first vertex, so benchmark rows already computed for such models stay valid (#53)."""
    obj, fan = tmp_path / "model_c.obj", tmp_path / "fan.obj"
    vertices = "v 0 0 0\nv 1 0 0\nv 2 1 0\nv 1 2 0\nv 0 1 0\nv 0.5 0.5 0\n"   # convex pentagon; a stray vertex, so the index mapping matters
    obj.write_text(vertices + "f 1 2 3 4 5\n")
    fan.write_text(vertices + "f 1 2 3\nf 1 3 4\nf 1 4 5\n")
    mesh, expected = load_model_mesh(obj), o3d.io.read_triangle_mesh(fan)
    assert np.array_equal(np.asarray(mesh.vertices), np.asarray(expected.vertices))
    assert np.array_equal(np.asarray(mesh.triangles), np.asarray(expected.triangles))


def test_load_model_mesh_triangulates_a_keyhole_face_to_its_exact_area(tmp_path: Path) -> None:
    """One face with repeated vertices, as in house_11 (#53): an L (area 27) with a quadrilateral hole (area 6) that touches the L's outline at (0,0) and at
    its reflex corner (3,3), so both are listed twice. Plain ear clipping accepts an ear whose diagonal runs through the hole and covers more than the face.
    Split at the repeated vertices it is two pentagons (6 triangles, not len(face) - 2 = 8: no hole remains to bridge)."""
    corners = [(0, 0), (6, 0), (6, 3), (3, 3), (3, 6), (0, 6), (1, 3), (3, 1)]   # OBJ vertices 1..8
    face = [1, 7, 4, 5, 6, 1, 2, 3, 4, 8]   # hole (1,3) then the outline from (3,3) round to (0,0), then back to the hole at (3,3) and (3,1)
    obj = tmp_path / "model_k.obj"
    obj.write_text("".join(f"v {x} {y} 0\n" for x, y in corners) + "f " + " ".join(map(str, face)) + "\n")
    mesh = load_model_mesh(obj)
    assert len(mesh.triangles) == 6
    assert mesh.get_surface_area() == pytest.approx(27 - 6)


def test_load_model_mesh_triangulates_a_square_with_a_hole_given_as_one_keyhole_face(tmp_path: Path) -> None:
    """A 4x4 square with a 2x2 hole as one face: outline counter-clockwise, bridge in to the hole, the hole clockwise, the bridge back, bridge
    vertices listed twice (#53). The hole stays empty and every triangle points along the face's normal (+z)."""
    corners = [(0, 0), (4, 0), (4, 4), (0, 4), (1, 1), (1, 3), (3, 3), (3, 1)]   # OBJ vertices 1..8
    face = [1, 2, 3, 4, 1, 5, 6, 7, 8, 5, 1]   # outline, bridge 1-5, hole (1,1) (1,3) (3,3) (3,1) back to (1,1), bridge 5-1
    obj = tmp_path / "model_h.obj"
    obj.write_text("".join(f"v {x} {y} 0\n" for x, y in corners) + "f " + " ".join(map(str, face)) + "\n")
    mesh = load_model_mesh(obj)
    assert mesh.get_surface_area() == pytest.approx(16 - 4)
    assert np.all(np.asarray(mesh.compute_triangle_normals().triangle_normals)[:, 2] > 0.99)


def test_load_model_mesh_does_not_fan_a_face_with_a_notch_below_the_convexity_tolerance(tmp_path: Path) -> None:
    """house_11's face 287170 (#53): a 10x1 rectangle with a 1 mm notch in its top edge. The notch's reflex turn is below the convexity
    tolerance, but a fan from (0,0) flips a long thin triangle across it, adding 2 x 0.00225 to the face's 10 - 5e-7."""
    corners = [(0, 0), (10, 0), (10, 1), (5.001, 1), (5.0005, 0.999), (5, 1), (0, 1)]
    obj = tmp_path / "model_n.obj"
    obj.write_text("".join(f"v {x} {y} 0\n" for x, y in corners) + "f 1 2 3 4 5 6 7\n")
    assert load_model_mesh(obj).get_surface_area() == pytest.approx(10 - 5e-7, abs=1e-9)


@pytest.mark.parametrize("tilted", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_load_model_mesh_triangulates_a_bowtie_to_the_area_it_covers(tmp_path: Path, tilted: bool, reverse: bool) -> None:
    """A quad with two corners swapped, its edges crossing (house_20, veh_012, veh_016; #53): corners (0,0) (2,2) (2,0) (0,3) cross at (1.2,1.2) into a lobe of
    area 1.8 (wound with the face) and one of area 0.8 (against it); the face covers 2.6, where the Newell area is 1.8 - 0.8 = 1. (A symmetric bowtie has
    Newell area 0, no plane, and stays a fan.) Every triangle, in the backward lobe too, faces along the Newell normal of the whole face."""
    corners = [(0, 0), (2, 2), (2, 0), (0, 3)]
    if reverse:
        corners.reverse()
    points = np.array([(x, y, 0.0) for x, y in corners])
    if tilted:
        points = points @ _rotation(0.7, (1, 2, 3)).T + np.array([5.0, -2.0, 1.0])
    newell = sum(np.cross(a, b) for a, b in zip(points, np.roll(points, -1, axis=0)))
    obj = tmp_path / "model_b.obj"
    obj.write_text("".join(f"v {x:.9f} {y:.9f} {z:.9f}\n" for x, y, z in points) + "f 1 2 3 4\n")
    mesh = load_model_mesh(obj)
    mesh.compute_triangle_normals()
    assert len(mesh.triangles) == 2
    assert mesh.get_surface_area() == pytest.approx(2.6, rel=1e-6)
    assert np.all(np.asarray(mesh.triangle_normals) @ newell > 0)


def test_load_model_mesh_keeps_later_faces_and_formats_valid_around_a_crossing_face(tmp_path: Path) -> None:
    """The crossing point of a bowtie is a new vertex: it goes at the end of the file, so a later face's relative indices still point at their vertices,
    and the triangles using it are written as plain `f a b c` (an OBJ face does not mix `v` and `v/vt/vn` tokens), whatever the other faces use (#53)."""
    obj = tmp_path / "model_m.obj"
    obj.write_text(
        "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\n"            # unit quad: area 1
        "v 0 0 0\nv 2 2 0\nv 2 0 0\nv 0 3 0\n"            # bowtie: area 2.6
        "v 10 0 0\nv 11 0 0\nv 10 1 0\n"                   # triangle by relative indices: area 0.5
        "vt 0 0\nvn 0 0 1\n"
        "f 1/1/1 2/1/1 3/1/1 4/1/1\n"
        "f 5/1/1 6/1/1 7/1/1 8/1/1\n"
        "f -3 -2 -1\n"
    )
    mesh = load_model_mesh(obj)
    assert len(mesh.triangles) == 2 + 2 + 1
    assert mesh.get_surface_area() == pytest.approx(1 + 2.6 + 0.5, rel=1e-6)
    assert [p.name for p in tmp_path.iterdir()] == ["model_m.obj"]


def test_load_model_mesh_appends_crossing_vertices_after_a_last_line_without_newline(tmp_path: Path) -> None:
    """A crossing face's new vertices go at the end of the file; an OBJ whose last line has no newline must not have them glued onto it."""
    obj = tmp_path / "model_e.obj"
    obj.write_text("v 0 0 0\nv 2 2 0\nv 2 0 0\nv 0 3 0\nv 5 0 0\nv 6 0 0\nv 5 1 0\nf 1 2 3 4\nf 5 6 7")
    assert load_model_mesh(obj).get_surface_area() == pytest.approx(2.6 + 0.5, rel=1e-6)


def test_non_triangle_share_counts_faces_open3d_drops(tmp_path: Path) -> None:
    """Open3D's OBJ reader skips every face that is not a triangle (veh_008: all quads, no triangles left); the share is what it drops."""
    obj = tmp_path / "m.obj"
    obj.write_text("v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf 1 2 3\nf 1/1/1 3/3/3 4/4/4\nf 1 2 3 4\n")
    assert non_triangle_share(obj) == 1 / 3

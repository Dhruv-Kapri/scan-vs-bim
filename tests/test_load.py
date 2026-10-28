import ifcopenshell
import ifcopenshell.api
import numpy as np
import pytest

from scan_vs_bim.load import ElementMesh, load_e57, load_ifc, load_ifc_elements, merge_meshes

OFFSET = (10.0, 20.0, 3.0)


def add_box(f, body, element, size, offset):
    """Give `element` an extruded rectangle (size x, y, z) placed at `offset` in the world."""
    x, y, z = size
    profile = f.createIfcRectangleProfileDef("AREA", None, f.createIfcAxis2Placement2D(f.createIfcCartesianPoint((x / 2, y / 2))), x, y)
    solid = f.createIfcExtrudedAreaSolid(profile, f.createIfcAxis2Placement3D(f.createIfcCartesianPoint((0.0, 0.0, 0.0))),
                                         f.createIfcDirection((0.0, 0.0, 1.0)), z)
    ifcopenshell.api.geometry.assign_representation(
        f, product=element, representation=f.createIfcShapeRepresentation(body, "Body", "SweptSolid", [solid]))
    m = np.eye(4)
    m[:3, 3] = offset
    ifcopenshell.api.geometry.edit_object_placement(f, product=element, matrix=m)


@pytest.fixture
def ifc_path(tmp_path):
    f = ifcopenshell.api.run("project.create_file")
    ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject", name="p")
    ifcopenshell.api.run("unit.assign_unit", f, length={"is_metric": True, "raw": "METERS"})
    ctx = ifcopenshell.api.run("context.add_context", f, context_type="Model")
    body = ifcopenshell.api.run("context.add_context", f, context_type="Model", context_identifier="Body",
                                target_view="MODEL_VIEW", parent=ctx)
    wall = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcWall")
    slab = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSlab")
    space = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSpace")
    add_box(f, body, wall, (4.0, 0.2, 3.0), OFFSET)
    add_box(f, body, slab, (4.0, 4.0, 0.3), (OFFSET[0], OFFSET[1] + 5, OFFSET[2]))
    add_box(f, body, space, (1.0, 1.0, 1.0), (0.0, 0.0, 0.0))
    path = tmp_path / "t.ifc"
    f.write(str(path))
    return path, {wall.GlobalId: "IfcWall", slab.GlobalId: "IfcSlab"}


def test_ifc_elements_identity_and_world_coords(ifc_path):
    path, expected = ifc_path
    els = load_ifc_elements(path)
    assert {e.global_id: e.ifc_class for e in els} == expected  # IfcSpace excluded
    wall = next(e for e in els if e.ifc_class == "IfcWall")
    assert isinstance(wall, ElementMesh) and wall.vertices.dtype == np.float64 and wall.faces.dtype == np.int32
    np.testing.assert_allclose(wall.vertices.min(0), OFFSET, atol=1e-6)
    np.testing.assert_allclose(wall.vertices.max(0), np.add(OFFSET, (4.0, 0.2, 3.0)), atol=1e-6)


def test_ifc_only_guids(ifc_path):
    path, expected = ifc_path
    wall_guid = next(g for g, c in expected.items() if c == "IfcWall")
    els = load_ifc_elements(path, only_guids=[wall_guid])
    assert [e.global_id for e in els] == [wall_guid]
    full = next(e for e in load_ifc_elements(path) if e.global_id == wall_guid)
    np.testing.assert_allclose(els[0].vertices, full.vertices)


def test_ifc_exclude_override(ifc_path):
    path, _ = ifc_path
    assert "IfcSpace" in {e.ifc_class for e in load_ifc_elements(path, exclude=())}


def test_ifc_only_guids_with_exclude_raises(ifc_path):
    path, expected = ifc_path
    with pytest.raises(ValueError):
        load_ifc_elements(path, only_guids=list(expected)[:1], exclude=("IfcSpace",))


def test_ifc_no_geometry_raises(tmp_path):
    f = ifcopenshell.api.run("project.create_file")
    ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject", name="p")
    path = tmp_path / "empty.ifc"
    f.write(str(path))
    with pytest.raises(RuntimeError):
        load_ifc_elements(path)


def test_merge_and_load_ifc(ifc_path):
    path, _ = ifc_path
    els = load_ifc_elements(path)
    mesh = merge_meshes(els)
    assert len(mesh.triangles) == sum(len(e.faces) for e in els)
    assert len(mesh.vertices) == sum(len(e.vertices) for e in els)
    assert mesh.has_vertex_normals() and not mesh.has_vertex_colors()
    assert np.asarray(mesh.triangles).max() < len(mesh.vertices)
    np.testing.assert_allclose(np.asarray(mesh.vertices)[np.asarray(mesh.triangles)],
                               np.concatenate([e.vertices[e.faces] for e in els]))  # faces keep their own element's vertices
    assert len(load_ifc(path).triangles) == len(mesh.triangles)


def write_e57(path, scans):
    """scans: list of (n_points, translation). Points are uniform in the unit cube."""
    import pye57

    rng = np.random.default_rng(1)
    e57 = pye57.E57(str(path), mode="w")
    for n, t in scans:
        data = {k: rng.random(n) for k in ("cartesianX", "cartesianY", "cartesianZ")}
        e57.write_scan_raw(data, rotation=np.array([1.0, 0, 0, 0]), translation=np.array(t, dtype=float))
    e57.close()


def test_e57_poses_proportional_and_seeded(tmp_path):
    path = tmp_path / "t.e57"
    write_e57(path, [(300, (100, 0, 0)), (100, (0, 200, 0))])
    pts = np.asarray(load_e57(path, max_points=100).points)
    assert len(pts) == 100
    near_a = pts[:, 0] > 50  # scan 0 sits near x=100, scan 1 near y=200
    assert near_a.sum() == 75 and (pts[~near_a, 1] > 150).all()
    assert (pts[near_a, 0] < 101).all()
    np.testing.assert_array_equal(pts, np.asarray(load_e57(path, max_points=100).points))
    assert not np.array_equal(pts, np.asarray(load_e57(path, max_points=100, seed=1).points))

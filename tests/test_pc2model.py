import io
import os
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np
import open3d as o3d
import pytest

from scan_vs_bim.fetch import data_start
from scan_vs_bim.pc2model import Sample, download_order, fetch_samples, group_samples, load_model_mesh, parse_transform, pick_gate_samples, pick_smallest_scaled, read_member, scale_of


def matrix_text(scale: float = 1.0, rotate: bool = False) -> str:
    R = np.eye(3)
    if rotate:  # 90 degrees about z
        R = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1.0]])
    T = np.eye(4)
    T[:3, :3] = scale * R
    T[:3, 3] = [215.8, -213.6, 492.5]
    return "\n".join(" ".join(f"{v:.6f}" for v in row) for row in T) + "\n"


def make_zip(samples: dict[str, tuple[float, bool, bytes]]) -> tuple[bytes, zipfile.ZipFile]:
    """samples: {folder: (scale, rotate, extra_bytes)}; returns (zip blob, ZipFile)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("Root/cat/"), b"")
        for folder, (scale, rotate, extra) in samples.items():
            name = folder.rsplit("/", 1)[-1]
            z.writestr(f"{folder}/transformation_matrix_pc2model_{name}.txt", matrix_text(scale, rotate))
            z.writestr(f"{folder}/pointcloud_{name}_transformed.e57", extra, compress_type=zipfile.ZIP_STORED)
    blob = buf.getvalue()
    return blob, zipfile.ZipFile(io.BytesIO(blob))


def reader_for(blob: bytes) -> Callable[[int, int], bytes]:
    return lambda start, end: blob[start : end + 1]


def test_parse_transform_reads_a_4x4() -> None:
    T = parse_transform(matrix_text(1.0))
    expected = np.eye(4)
    expected[:3, 3] = [215.8, -213.6, 492.5]
    assert T.dtype == np.float64
    np.testing.assert_allclose(T, expected)


def test_parse_transform_wrong_shape() -> None:
    with pytest.raises(ValueError, match="4x4"):
        parse_transform("1 0 0\n0 1 0\n0 0 1\n")


@pytest.mark.parametrize(("scale", "rotate"), [(0.8, True), (1.3, False), (1.0, True)])
def test_scale_of_is_the_uniform_scale_whatever_the_rotation(scale: float, rotate: bool) -> None:
    assert scale_of(parse_transform(matrix_text(scale, rotate))) == pytest.approx(scale)


def test_group_samples_finds_each_transform_and_skips_dirs() -> None:
    blob, z = make_zip({"Root/cat/a": (1.0, False, os.urandom(50)), "Root/cat/b": (1.2, False, os.urandom(50))})
    samples = {s.folder: s for s in group_samples(z.infolist())}
    assert set(samples) == {"Root/cat/a", "Root/cat/b"}
    assert samples["Root/cat/a"].transform.filename.endswith("transformation_matrix_pc2model_a.txt")


def test_group_samples_sums_compressed_sizes_per_folder() -> None:
    blob, z = make_zip({"Root/cat/a": (1.0, False, os.urandom(500)), "Root/cat/b": (1.2, False, os.urandom(100))})
    samples = {s.folder: s for s in group_samples(z.infolist())}
    for folder, sample in samples.items():
        assert sample.compressed_size == sum(i.compress_size for i in z.infolist() if i.filename.startswith(folder + "/"))


def test_group_samples_drops_folders_without_transform() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Root/cat/a/pointcloud_a.e57", b"x")
        zf.writestr("Root/cat/b/transformation_matrix_pc2model_b.txt", matrix_text())
    samples = group_samples(zipfile.ZipFile(io.BytesIO(buf.getvalue())).infolist())
    assert [s.folder for s in samples] == ["Root/cat/b"]


def test_read_member_reads_deflated_member() -> None:
    blob, z = make_zip({"Root/cat/a": (1.0, False, b"x")})
    s = group_samples(z.infolist())[0]
    assert read_member(reader_for(blob), s.transform).decode() == matrix_text(1.0)


def test_read_member_reads_stored_member() -> None:
    payload = os.urandom(300)
    blob, z = make_zip({"Root/cat/a": (1.0, False, payload)})
    stored = z.getinfo("Root/cat/a/pointcloud_a_transformed.e57")
    assert read_member(reader_for(blob), stored) == payload


def test_read_member_raises_on_crc_mismatch() -> None:
    blob, z = make_zip({"Root/cat/a": (1.0, False, b"x")})
    info = z.getinfo("Root/cat/a/pointcloud_a_transformed.e57")
    bad = bytearray(blob)
    bad[data_start(reader_for(blob), info)] ^= 0xFF
    with pytest.raises(ValueError, match="CRC"):
        read_member(reader_for(bytes(bad)), info)


def test_pick_smallest_scaled_picks_smallest_scaled_sample() -> None:
    blob, z = make_zip({"Root/cat/big": (1.3, False, os.urandom(5000)), "Root/cat/small": (0.6, True, os.urandom(800))})
    samples = group_samples(z.infolist())
    scales = {"Root/cat/big": 1.3, "Root/cat/small": 0.6}
    assert pick_smallest_scaled(samples, scales).folder == "Root/cat/small"


def test_pick_smallest_scaled_ignores_unscaled_samples_within_tol() -> None:
    blob, z = make_zip({"Root/cat/tiny": (1.0, True, os.urandom(10)), "Root/cat/big": (1.3, False, os.urandom(5000))})
    samples = group_samples(z.infolist())
    scales = {"Root/cat/tiny": 1.0 + 1e-4, "Root/cat/big": 1.3}
    assert pick_smallest_scaled(samples, scales).folder == "Root/cat/big"


def test_pick_smallest_scaled_raises_when_none_scaled() -> None:
    blob, z = make_zip({"Root/cat/a": (1.0, True, b"x")})
    samples = group_samples(z.infolist())
    with pytest.raises(ValueError, match="no scaled sample"):
        pick_smallest_scaled(samples, {"Root/cat/a": 1.0})


def fake_samples(spec: dict[str, tuple[str, int, float]]) -> tuple[list[Sample], dict[str, float]]:
    """spec: {sample name: (category, compressed bytes, scale)} -> (samples, scales) with PC2Model-style folders."""
    samples: list[Sample] = []
    scales: dict[str, float] = {}
    for name, (category, size, scale) in spec.items():
        folder = f"Root/{category}/{name}"
        samples.append(Sample(folder, size, zipfile.ZipInfo("t.txt")))
        scales[folder] = scale
    return samples, scales


def test_sample_category_is_the_folder_segment_under_the_root() -> None:
    assert Sample("PC2Model_v1.4/house/house_23-sketchfab", 1, zipfile.ZipInfo("t.txt")).category == "house"


def test_pick_gate_samples_takes_smallest_scaled_smallest_unscaled_then_next_smallest() -> None:
    samples, scales = fake_samples({
        "a": ("cat", 10, 1.0),   # smallest unscaled
        "b": ("cat", 20, 1.0),   # next smallest remaining
        "c": ("cat", 30, 1.4),   # smallest scaled
        "d": ("cat", 40, 0.7),
    })
    picked = pick_gate_samples(samples, scales, categories=["cat"])
    assert [s.folder.rsplit("/", 1)[-1] for s in picked] == ["c", "a", "b"]


def test_pick_gate_samples_follows_category_order_and_ignores_other_categories() -> None:
    samples, scales = fake_samples({
        "x1": ("other", 1, 1.0), "x2": ("other", 2, 2.0), "x3": ("other", 3, 1.0),
        "h1": ("house", 10, 1.0), "h2": ("house", 20, 1.5), "h3": ("house", 30, 1.0),
        "i1": ("indoor", 11, 1.0), "i2": ("indoor", 22, 0.8), "i3": ("indoor", 33, 1.0),
    })
    picked = pick_gate_samples(samples, scales, categories=["indoor", "house"])
    assert [s.folder.rsplit("/", 1)[-1] for s in picked] == ["i2", "i1", "i3", "h2", "h1", "h3"]


def test_pick_gate_samples_is_independent_of_input_order_and_breaks_size_ties_by_folder() -> None:
    samples, scales = fake_samples({
        "b": ("cat", 10, 1.0), "a": ("cat", 10, 1.0), "c": ("cat", 10, 1.3), "d": ("cat", 99, 1.0),
    })
    def names(ss: Sequence[Sample]) -> list[str]:
        return [s.folder.rsplit("/", 1)[-1] for s in ss]
    forward = names(pick_gate_samples(samples, scales, categories=["cat"]))
    backward = names(pick_gate_samples(samples[::-1], scales, categories=["cat"]))
    assert forward == backward == ["c", "a", "b"]


@pytest.mark.parametrize("spec, message", [
    ({"a": ("cat", 1, 1.0), "b": ("cat", 2, 1.0), "c": ("cat", 3, 1.0)}, "no scaled sample"),
    ({"a": ("cat", 1, 1.5), "b": ("cat", 2, 1.4), "c": ("cat", 3, 1.3)}, "no unscaled sample"),
    ({"a": ("cat", 1, 1.5), "b": ("cat", 2, 1.0)}, "fewer than 3"),
])
def test_pick_gate_samples_raises_when_a_category_cannot_give_three(spec: dict[str, tuple[str, int, float]], message: str) -> None:
    samples, scales = fake_samples(spec)
    with pytest.raises(ValueError, match=message):
        pick_gate_samples(samples, scales, categories=["cat"])


def test_download_order_puts_buildings_first_and_keeps_input_order() -> None:
    rows = [
        {"sample": "Z/furniture/chair", "category": "furniture"},
        {"sample": "Z/house/h1", "category": "house"},
        {"sample": "Z/vehicle/car", "category": "vehicle"},
        {"sample": "Z/ISPRS_indoor_modeling_benchmark/i1", "category": "ISPRS_indoor_modeling_benchmark"},
        {"sample": "Z/indoor_modelling/m1", "category": "indoor_modelling"},
        {"sample": "Z/house/h2", "category": "house"},
        {"sample": "Z/furniture/desk", "category": "furniture"},
    ]
    assert download_order(rows) == [
        "Z/house/h1",
        "Z/ISPRS_indoor_modeling_benchmark/i1",
        "Z/indoor_modelling/m1",
        "Z/house/h2",
        "Z/furniture/chair",
        "Z/vehicle/car",
        "Z/furniture/desk",
    ]


def _two_sample_zip() -> tuple[bytes, list[zipfile.ZipInfo], dict[str, bytes]]:
    files = {
        "Z/house/a/scan.txt": os.urandom(500),
        "Z/house/a/transformation_matrix.txt": b"1 0 0 0\n",
        "Z/furniture/b/scan.txt": os.urandom(700),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Z/house/a/", b"")
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue(), zipfile.ZipFile(io.BytesIO(buf.getvalue())).infolist(), files


def test_fetch_samples_extracts_in_order_then_skips_complete_files(tmp_path: Path) -> None:
    blob, infos, files = _two_sample_zip()
    calls: list[tuple[int, int]] = []

    def read_range(start: int, end: int) -> bytes:
        calls.append((start, end))
        return blob[start : end + 1]

    fetch_samples(read_range, infos, ["Z/furniture/b", "Z/house/a"], tmp_path)
    assert (tmp_path / "b" / "scan.txt").read_bytes() == files["Z/furniture/b/scan.txt"]
    assert (tmp_path / "a" / "scan.txt").read_bytes() == files["Z/house/a/scan.txt"]
    assert (tmp_path / "a" / "transformation_matrix.txt").read_bytes() == files["Z/house/a/transformation_matrix.txt"]
    furniture = next(i for i in infos if i.filename == "Z/furniture/b/scan.txt")
    assert calls[0][0] == furniture.header_offset  # the first read is the first folder listed, though it is last in the zip
    calls.clear()
    fetch_samples(read_range, infos, ["Z/furniture/b", "Z/house/a"], tmp_path)
    assert calls == []


def test_fetch_samples_rejects_a_folder_missing_from_the_zip(tmp_path: Path) -> None:
    _, infos, _ = _two_sample_zip()
    with pytest.raises(ValueError, match="Z/house/nope"):
        fetch_samples(lambda s, e: b"", infos, ["Z/house/nope"], tmp_path)


def test_load_model_mesh_keeps_the_area_of_quads_and_ngons(tmp_path: Path) -> None:
    """Open3D's reader drops every non-triangle face (#53); the loader fans them into triangles, whatever the token form."""
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

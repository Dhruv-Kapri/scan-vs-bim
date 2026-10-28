import io
import os
import zipfile

import numpy as np
import pytest

from scan_vs_bim.fetch import data_start
from scan_vs_bim.pc2model import group_samples, parse_transform, pick_smallest_scaled, read_member, scale_of


def matrix_text(scale=1.0, rotate=False):
    R = np.eye(3)
    if rotate:  # 90 degrees about z
        R = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1.0]])
    T = np.eye(4)
    T[:3, :3] = scale * R
    T[:3, 3] = [215.8, -213.6, 492.5]
    return "\n".join(" ".join(f"{v:.6f}" for v in row) for row in T) + "\n"


def make_zip(samples):
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


def reader_for(blob):
    return lambda start, end: blob[start : end + 1]


def test_parse_transform_and_scale():
    T = parse_transform(matrix_text(0.8, rotate=True))
    assert T.shape == (4, 4) and T.dtype == np.float64
    assert scale_of(T) == pytest.approx(0.8)


def test_rotation_alone_is_not_scale():
    assert scale_of(parse_transform(matrix_text(1.0, rotate=True))) == pytest.approx(1.0)


def test_parse_transform_wrong_shape():
    with pytest.raises(ValueError):
        parse_transform("1 0 0\n0 1 0\n0 0 1\n")


def test_group_samples_sizes_and_transform():
    blob, z = make_zip({"Root/cat/a": (1.0, False, os.urandom(500)), "Root/cat/b": (1.2, False, os.urandom(100))})
    samples = {s.folder: s for s in group_samples(z.infolist())}
    assert set(samples) == {"Root/cat/a", "Root/cat/b"}
    a = samples["Root/cat/a"]
    assert a.transform.filename.endswith("transformation_matrix_pc2model_a.txt")
    assert a.compressed_size == sum(i.compress_size for i in z.infolist() if i.filename.startswith("Root/cat/a/"))


def test_read_member_deflated_and_stored():
    payload = os.urandom(300)
    blob, z = make_zip({"Root/cat/a": (1.0, False, payload)})
    s = group_samples(z.infolist())[0]
    assert read_member(reader_for(blob), s.transform).decode() == matrix_text(1.0)
    stored = z.getinfo("Root/cat/a/pointcloud_a_transformed.e57")
    assert read_member(reader_for(blob), stored) == payload


def test_read_member_crc_mismatch():
    blob, z = make_zip({"Root/cat/a": (1.0, False, b"x")})
    info = z.getinfo("Root/cat/a/pointcloud_a_transformed.e57")
    bad = bytearray(blob)
    bad[data_start(reader_for(blob), info)] ^= 0xFF
    with pytest.raises(ValueError, match="CRC"):
        read_member(reader_for(bytes(bad)), info)


def test_pick_smallest_scaled():
    blob, z = make_zip(
        {
            "Root/cat/tiny_unscaled": (1.0, True, os.urandom(10)),
            "Root/cat/big_scaled": (1.3, False, os.urandom(5000)),
            "Root/cat/small_scaled": (0.6, True, os.urandom(800)),
        }
    )
    samples = group_samples(z.infolist())
    scales = {s.folder: scale_of(parse_transform(read_member(reader_for(blob), s.transform).decode())) for s in samples}
    assert pick_smallest_scaled(samples, scales).folder == "Root/cat/small_scaled"


def test_pick_none_scaled_raises():
    blob, z = make_zip({"Root/cat/a": (1.0, True, b"x")})
    samples = group_samples(z.infolist())
    with pytest.raises(ValueError):
        pick_smallest_scaled(samples, {"Root/cat/a": 1.0})

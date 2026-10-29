import io
import os
import zipfile

import numpy as np
import pytest

from scan_vs_bim.fetch import data_start
from scan_vs_bim.pc2model import Sample, group_samples, parse_transform, pick_gate_samples, pick_smallest_scaled, read_member, scale_of


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


def test_parse_transform_reads_a_4x4():
    T = parse_transform(matrix_text(1.0))
    assert T.shape == (4, 4) and T.dtype == np.float64
    assert T[0, 3] == pytest.approx(215.8)


def test_parse_transform_wrong_shape():
    with pytest.raises(ValueError):
        parse_transform("1 0 0\n0 1 0\n0 0 1\n")


def test_scale_of_returns_s_for_scaled_rotation():
    T = parse_transform(matrix_text(0.8))
    assert scale_of(T) == pytest.approx(0.8)


def test_rotation_alone_is_scale_one():
    assert scale_of(parse_transform(matrix_text(1.0, rotate=True))) == pytest.approx(1.0)


def test_group_samples_finds_each_transform_and_skips_dirs():
    blob, z = make_zip({"Root/cat/a": (1.0, False, os.urandom(50)), "Root/cat/b": (1.2, False, os.urandom(50))})
    samples = {s.folder: s for s in group_samples(z.infolist())}
    assert set(samples) == {"Root/cat/a", "Root/cat/b"}
    assert samples["Root/cat/a"].transform.filename.endswith("transformation_matrix_pc2model_a.txt")


def test_group_samples_sums_compressed_sizes_per_folder():
    blob, z = make_zip({"Root/cat/a": (1.0, False, os.urandom(500)), "Root/cat/b": (1.2, False, os.urandom(100))})
    samples = {s.folder: s for s in group_samples(z.infolist())}
    for folder, sample in samples.items():
        assert sample.compressed_size == sum(i.compress_size for i in z.infolist() if i.filename.startswith(folder + "/"))


def test_group_samples_drops_folders_without_transform():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Root/cat/a/pointcloud_a.e57", b"x")
        zf.writestr("Root/cat/b/transformation_matrix_pc2model_b.txt", matrix_text())
    samples = group_samples(zipfile.ZipFile(io.BytesIO(buf.getvalue())).infolist())
    assert [s.folder for s in samples] == ["Root/cat/b"]


def test_read_member_reads_deflated_member():
    blob, z = make_zip({"Root/cat/a": (1.0, False, b"x")})
    s = group_samples(z.infolist())[0]
    assert read_member(reader_for(blob), s.transform).decode() == matrix_text(1.0)


def test_read_member_reads_stored_member():
    payload = os.urandom(300)
    blob, z = make_zip({"Root/cat/a": (1.0, False, payload)})
    stored = z.getinfo("Root/cat/a/pointcloud_a_transformed.e57")
    assert read_member(reader_for(blob), stored) == payload


def test_read_member_raises_on_crc_mismatch():
    blob, z = make_zip({"Root/cat/a": (1.0, False, b"x")})
    info = z.getinfo("Root/cat/a/pointcloud_a_transformed.e57")
    bad = bytearray(blob)
    bad[data_start(reader_for(blob), info)] ^= 0xFF
    with pytest.raises(ValueError, match="CRC"):
        read_member(reader_for(bytes(bad)), info)


def test_pick_smallest_scaled_picks_smallest_scaled_sample():
    blob, z = make_zip({"Root/cat/big": (1.3, False, os.urandom(5000)), "Root/cat/small": (0.6, True, os.urandom(800))})
    samples = group_samples(z.infolist())
    scales = {"Root/cat/big": 1.3, "Root/cat/small": 0.6}
    assert pick_smallest_scaled(samples, scales).folder == "Root/cat/small"


def test_pick_smallest_scaled_ignores_unscaled_samples_within_tol():
    blob, z = make_zip({"Root/cat/tiny": (1.0, True, os.urandom(10)), "Root/cat/big": (1.3, False, os.urandom(5000))})
    samples = group_samples(z.infolist())
    scales = {"Root/cat/tiny": 1.0 + 1e-4, "Root/cat/big": 1.3}
    assert pick_smallest_scaled(samples, scales).folder == "Root/cat/big"


def test_pick_smallest_scaled_raises_when_none_scaled():
    blob, z = make_zip({"Root/cat/a": (1.0, True, b"x")})
    samples = group_samples(z.infolist())
    with pytest.raises(ValueError, match="no scaled sample"):
        pick_smallest_scaled(samples, {"Root/cat/a": 1.0})


def fake_samples(spec):
    """spec: {sample name: (category, compressed bytes, scale)} -> (samples, scales) with PC2Model-style folders."""
    samples, scales = [], {}
    for name, (category, size, scale) in spec.items():
        folder = f"Root/{category}/{name}"
        samples.append(Sample(folder, size, zipfile.ZipInfo("t.txt")))
        scales[folder] = scale
    return samples, scales


def test_pick_gate_samples_takes_smallest_scaled_smallest_unscaled_then_next_smallest():
    samples, scales = fake_samples({
        "a": ("cat", 10, 1.0),   # smallest unscaled
        "b": ("cat", 20, 1.0),   # next smallest remaining
        "c": ("cat", 30, 1.4),   # smallest scaled
        "d": ("cat", 40, 0.7),
    })
    picked = pick_gate_samples(samples, scales, categories=["cat"])
    assert [s.folder.rsplit("/", 1)[-1] for s in picked] == ["c", "a", "b"]


def test_pick_gate_samples_follows_category_order_and_ignores_other_categories():
    samples, scales = fake_samples({
        "x1": ("other", 1, 1.0), "x2": ("other", 2, 2.0), "x3": ("other", 3, 1.0),
        "h1": ("house", 10, 1.0), "h2": ("house", 20, 1.5), "h3": ("house", 30, 1.0),
        "i1": ("indoor", 11, 1.0), "i2": ("indoor", 22, 0.8), "i3": ("indoor", 33, 1.0),
    })
    picked = pick_gate_samples(samples, scales, categories=["indoor", "house"])
    assert [s.folder.rsplit("/", 1)[-1] for s in picked] == ["i2", "i1", "i3", "h2", "h1", "h3"]


def test_pick_gate_samples_is_independent_of_input_order_and_breaks_size_ties_by_folder():
    samples, scales = fake_samples({
        "b": ("cat", 10, 1.0), "a": ("cat", 10, 1.0), "c": ("cat", 10, 1.3), "d": ("cat", 99, 1.0),
    })
    names = lambda ss: [s.folder.rsplit("/", 1)[-1] for s in ss]
    forward = names(pick_gate_samples(samples, scales, categories=["cat"]))
    backward = names(pick_gate_samples(samples[::-1], scales, categories=["cat"]))
    assert forward == backward == ["c", "a", "b"]


@pytest.mark.parametrize("spec, message", [
    ({"a": ("cat", 1, 1.0), "b": ("cat", 2, 1.0), "c": ("cat", 3, 1.0)}, "no scaled sample"),
    ({"a": ("cat", 1, 1.5), "b": ("cat", 2, 1.4), "c": ("cat", 3, 1.3)}, "no unscaled sample"),
    ({"a": ("cat", 1, 1.5), "b": ("cat", 2, 1.0)}, "fewer than 3"),
])
def test_pick_gate_samples_raises_when_a_category_cannot_give_three(spec, message):
    samples, scales = fake_samples(spec)
    with pytest.raises(ValueError, match=message):
        pick_gate_samples(samples, scales, categories=["cat"])

import json
import os
import zipfile

import numpy as np
import pytest

from scan_vs_bim import cras_cache
from scan_vs_bim.cras_cache import build_cache

MEMBER = "CRASLAB_annotated.asc"
# x y z r g b intensity class
ROWS = [
    (0.0012, 0.0034, 0.0056, 10, 20, 30, 0.5, 1.0),  # voxel A, first
    (0.0090, 0.0010, 0.0020, 11, 21, 31, 0.6, 2.0),  # voxel A again: dropped
    (0.0123, 0.0034, 0.0056, 40, 50, 60, 0.1, 7.0),  # voxel B (x one cell over)
    (-0.0050, -0.0120, 3.2100, 70, 80, 90, 0.2, 33.0),  # negative coords
    (-0.0090, -0.0110, 3.2190, 71, 81, 91, 0.2, 5.0),  # same negative voxel: dropped
    (6.5185, 15.7385, 1.5075, 164, 174, 193, 0.201, 12.0),
]


def asc_text(rows, declared=None, eol="\n"):
    lines = ["//X Y Z R G B Intensity Classification".replace(" ", "\t"), str(declared or len(rows))]
    lines += ["\t".join(str(v) for v in r) for r in rows]
    return eol.join(lines) + eol


def make_zip(path, text, method, name=MEMBER):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(zipfile.ZipInfo(name), text, compress_type=method)


METHODS = [zipfile.ZIP_DEFLATED, zipfile.ZIP_STORED]


def load(path):
    with np.load(path) as d:
        return d["xyz"], d["rgb"], d["cls"], json.loads(str(d["meta"]))


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_voxel_first_point_wins_and_attributes_kept(tmp_path, method, eol):
    zpath, out = tmp_path / "t.zip", tmp_path / "c.npz"
    make_zip(zpath, asc_text(ROWS, eol=eol), method)
    # 37 bytes: lines straddle blocks, so do the header and count lines.
    meta = build_cache(zpath, out, voxel=0.01, chunk_bytes=37)
    xyz, rgb, cls, saved = load(out)

    keep = [0, 2, 3, 5]
    assert xyz.dtype == np.float32 and rgb.dtype == np.uint8 and cls.dtype == np.uint8
    by_x = np.argsort(xyz[:, 0])  # kept order is not part of the contract
    want = sorted(keep, key=lambda i: ROWS[i][0])
    np.testing.assert_allclose(xyz[by_x], [ROWS[i][:3] for i in want], rtol=1e-6)
    assert rgb[by_x].tolist() == [list(ROWS[i][3:6]) for i in want]
    assert cls[by_x].tolist() == [int(ROWS[i][7]) for i in want]
    assert saved == meta


@pytest.mark.parametrize("method", METHODS)
def test_metadata_and_header_not_parsed_as_points(tmp_path, method):
    zpath, out = tmp_path / "t.zip", tmp_path / "c.npz"
    make_zip(zpath, asc_text(ROWS), method)
    meta = build_cache(zpath, out, voxel=0.01, chunk_bytes=64)
    assert meta["voxel_size"] == 0.01
    assert meta["member"] == MEMBER
    with zipfile.ZipFile(zpath) as z:
        assert meta["member_size"] == z.getinfo(MEMBER).file_size
    assert meta["points_read"] == len(ROWS)
    assert meta["points_declared"] == len(ROWS)
    assert meta["points_kept"] == 4
    assert meta["extent_min"] == pytest.approx([-0.005, -0.012, 0.0056], abs=1e-6)
    assert meta["extent_max"] == pytest.approx([6.5185, 15.7385, 3.21], abs=1e-4)


def test_rerun_is_a_noop_without_streaming(tmp_path, monkeypatch):
    zpath, out = tmp_path / "t.zip", tmp_path / "c.npz"
    make_zip(zpath, asc_text(ROWS), zipfile.ZIP_DEFLATED)
    first = build_cache(zpath, out)
    before = os.stat(out).st_mtime_ns

    real_open = zipfile.ZipFile.open

    def guarded(self, name, *a, **k):  # np.load opens the npz members through this too
        if getattr(name, "filename", name) == MEMBER:
            raise AssertionError("should not stream")
        return real_open(self, name, *a, **k)

    monkeypatch.setattr(zipfile.ZipFile, "open", guarded)
    assert build_cache(zpath, out) == first
    assert os.stat(out).st_mtime_ns == before


def test_rebuilds_when_voxel_changes(tmp_path):
    zpath, out = tmp_path / "t.zip", tmp_path / "c.npz"
    make_zip(zpath, asc_text(ROWS), zipfile.ZIP_STORED)
    assert build_cache(zpath, out, voxel=0.01)["points_kept"] == 4
    assert build_cache(zpath, out, voxel=0.0001)["points_kept"] == len(ROWS)


def test_dedupe_across_many_blocks_keeps_stream_first(tmp_path, monkeypatch):
    """Consolidation must let earlier rows win, across blocks and merges."""
    monkeypatch.setattr(cras_cache, "MIN_PENDING", 4)
    rng = np.random.default_rng(0)
    xyz = rng.uniform(-1, 1, (3000, 3)).round(4)
    rows = [(*p, i % 256, 0, 0, 0.0, float(i % 34)) for i, p in enumerate(xyz)]
    zpath, out = tmp_path / "t.zip", tmp_path / "c.npz"
    make_zip(zpath, asc_text(rows), zipfile.ZIP_DEFLATED)
    build_cache(zpath, out, voxel=0.25, chunk_bytes=500)
    got, rgb, _, _ = load(out)

    first = {}
    for p, r in zip(xyz, rows):
        first.setdefault(tuple(np.floor(p / 0.25).astype(int)), r[3])
    assert len(got) == len(first)
    for p, c in zip(got, rgb[:, 0]):
        assert first[tuple(np.floor(p.astype(np.float64) / 0.25).astype(int))] == c


def test_rejects_zip_without_exactly_one_member(tmp_path):
    zpath = tmp_path / "t.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("a.asc", asc_text(ROWS))
        z.writestr("b.asc", asc_text(ROWS))
    with pytest.raises(ValueError, match="one member"):
        build_cache(zpath, tmp_path / "c.npz")


def test_truncated_stream_raises_and_writes_no_cache(tmp_path):
    zpath, out = tmp_path / "t.zip", tmp_path / "c.npz"
    make_zip(zpath, asc_text(ROWS, declared=len(ROWS) + 1), zipfile.ZIP_DEFLATED)
    with pytest.raises(ValueError, match="declares"):
        build_cache(zpath, out)
    assert not out.exists() and not out.with_name("c.npz.tmp").exists()


@pytest.mark.parametrize(
    "text",
    ["X\tY\tZ\n3\n1\t2\t3\t4\t5\t6\t7\t8\n", "//X Y Z\nthree\n1\t2\t3\t4\t5\t6\t7\t8\n"],
    ids=["header", "count"],
)
def test_malformed_header_or_count_raises(tmp_path, text):
    zpath = tmp_path / "t.zip"
    make_zip(zpath, text, zipfile.ZIP_STORED)
    with pytest.raises(ValueError, match="header|count"):
        build_cache(zpath, tmp_path / "c.npz")

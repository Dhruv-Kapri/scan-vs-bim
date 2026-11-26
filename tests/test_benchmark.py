import csv
import math
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from scan_vs_bim.benchmark import COLUMNS, _row, run_benchmark, score_sample, seen_mark

ROOT: Path = Path(__file__).resolve().parent.parent
SCRIPT: Path = ROOT / "scripts" / "run_benchmark.py"
SCALES: Path = ROOT / "outputs" / "pc2model_scales.csv"
GATE: Path = ROOT / "outputs" / "05a" / "gate_samples.csv"
FUR_010: str = "PC2Model_v1.4/furniture/fur_010-modelnet"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_benchmark", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_seen_mark_gate_wins_over_tuning() -> None:
    assert seen_mark("a", {"a"}, {"a"}) == "gate"
    assert seen_mark("b", {"a"}, {"b"}) == "tuning"
    assert seen_mark("c", {"a"}, {"b"}) == "unseen"


def test_fur_010_end_to_end_and_resume(tmp_path: Path) -> None:
    """One sample through the script: a full row, and a second run skips it (the file is untouched)."""
    needs = [SCALES, GATE, ROOT / "data" / "pc2model" / "fur_010-modelnet"]
    for p in needs:
        if not p.exists():
            pytest.skip(f"{p.relative_to(ROOT)} missing (run find_scaled_sample.py --no-fetch, pick_gate_samples.py, fetch_all_samples.py)")
    out = tmp_path / "registration.csv"
    args = ["--only", FUR_010, "--out", str(out), "--scales", str(SCALES), "--gate", str(GATE), "--data", str(ROOT / "data" / "pc2model")]
    mod = _load_script()
    mod.main(args)
    with out.open(newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert reader.fieldnames == COLUMNS
    assert len(rows) == 1
    assert rows[0]["seen"] == "tuning" and rows[0]["category"] == "furniture"
    before = out.read_bytes()
    mod.main(args)
    assert out.read_bytes() == before


def test_failing_samples_are_returned_and_the_run_continues(tmp_path: Path) -> None:
    folders = ["PC2Model_v1.4/furniture/nope_1", "PC2Model_v1.4/furniture/nope_2"]
    out = tmp_path / "registration.csv"
    failed = run_benchmark(folders, tmp_path / "no-data", out, set(), set(), "abc1234")
    assert failed == folders


def test_a_model_with_no_triangles_is_a_failed_row_not_a_skipped_sample(tmp_path: Path) -> None:
    """A model with no faces at all cannot be registered by 05a's pipeline; that is a failure of the
    pipeline, scored as such (errors NaN, success False), not a sample left out of the benchmark."""
    d = tmp_path / "veh_9-x"
    d.mkdir()
    (d / "model_veh_9-x.obj").write_text("v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\n")
    (d / "transformation_matrix_veh_9-x.txt").write_text("2 0 0 0\n0 2 0 0\n0 0 2 0\n0 0 0 1\n")
    (d / "pointcloud_veh_9-x_transformed.e57").write_bytes(b"")   # never read: the model fails first
    row = score_sample("PC2Model_v1.4/vehicle/veh_9-x", tmp_path, "unseen", "abc1234")
    assert list(row) == COLUMNS
    assert row["success"] is False and row["seed0_success"] is False and row["scaled"] is True
    assert all(math.isnan(float(str(row[k]))) for k in ("rot_deg", "centroid_m", "scale_err_pct", "est_scale"))


def test_a_row_must_set_every_column_and_only_columns() -> None:
    who = dict.fromkeys(["sample", "folder", "category", "seen", "scaled", "gt_scale", "load_s", "run_s", "peak_rss_gb", "commit"], "x")
    assert list(_row(**who)) == COLUMNS   # the measurements default to "not registered"
    with pytest.raises(ValueError, match="commit"):
        _row(**{k: v for k, v in who.items() if k != "commit"})
    with pytest.raises(ValueError, match="rot_degrees"):
        _row(**who, rot_degrees=1.0)

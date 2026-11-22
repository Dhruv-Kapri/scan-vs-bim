import csv
import math
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from scan_vs_bim.benchmark import COLUMNS, gate_agreement, non_triangle_share, results_markdown, run_benchmark, score_sample, seen_mark

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


def _row(folder: str, category: str, seen: str = "unseen", scaled: bool = False, success: bool = True, seed0: bool = True,
         rot: float = 0.1, cen: float = 0.01, scale_err: float = 0.1) -> dict[str, str]:
    return {"sample": Path(folder).name, "folder": folder, "category": category, "seen": seen, "scaled": str(scaled),
            "rot_deg": str(rot), "centroid_m": str(cen), "scale_err_pct": str(scale_err), "success": str(success),
            "seed0_success": str(seed0), "run_s": "60", "peak_rss_gb": "0.4", "commit": "abc1234"}


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


def test_unseen_rates_exclude_gate_and_tuning_and_scaled_is_split() -> None:
    rows = [
        _row("PC2Model_v1.4/house/h_1", "house", "gate", success=True),
        _row("PC2Model_v1.4/house/h_2", "house", "unseen", success=False),
        _row("PC2Model_v1.4/house/h_3", "house", "unseen", scaled=True, success=True),
        _row("PC2Model_v1.4/furniture/f_1", "furniture", "tuning", success=True),
    ]
    md = results_markdown(rows, [], "CMD", expected=[], non_triangle={})
    house = [ln for ln in md.splitlines() if ln.startswith("| house")]
    unscaled, scaled = house[0], house[1]
    assert "unscaled" in unscaled and "scaled" in scaled and "unscaled" not in scaled
    assert "1/2" in unscaled and "0/1" in unscaled   # all samples 1/2; unseen only 0/1 (the gate row is out)
    assert "1/1" in scaled
    assert "CMD" in md and "abc1234" in md


def test_gate_agreement_flags_a_changed_or_missing_row() -> None:
    f1, f2 = "PC2Model_v1.4/house/h_1", "PC2Model_v1.4/house/h_2"
    gate = [{"sample": "h_1", "success": "True", "rot_deg": "0.1", "centroid_m": "0.01", "scale_err_pct": "0.1"},
            {"sample": "h_2", "success": "True", "rot_deg": "0.1", "centroid_m": "0.01", "scale_err_pct": "0.1"}]
    same = [_row(f1, "house"), _row(f2, "house")]
    assert all(a["agrees"] for a in gate_agreement(same, gate))
    changed = [_row(f1, "house"), _row(f2, "house", success=False)]
    assert [a["agrees"] for a in gate_agreement(changed, gate)] == [True, False]
    assert [a["agrees"] for a in gate_agreement(same[:1], gate)] == [True, False]
    assert "all agree: no" in results_markdown(changed, gate, "CMD", expected=[], non_triangle={})
    assert "all agree: yes" in results_markdown(same, gate, "CMD", expected=[], non_triangle={})


def test_non_triangle_share_counts_faces_open3d_drops(tmp_path: Path) -> None:
    """Open3D's OBJ reader skips every face that is not a triangle (veh_008: all quads, no triangles left); the share is what it drops."""
    obj = tmp_path / "m.obj"
    obj.write_text("v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf 1 2 3\nf 1/1/1 3/3/3 4/4/4\nf 1 2 3 4\n")
    assert non_triangle_share(obj) == 1 / 3


def test_results_list_unscored_samples_and_models_losing_faces() -> None:
    rows = [_row("PC2Model_v1.4/house/h_1", "house"), _row("PC2Model_v1.4/house/h_2", "house", success=False)]
    md = results_markdown(rows, [], "CMD", expected=[r["folder"] for r in rows] + ["PC2Model_v1.4/vehicle/v_9"],
                          non_triangle={"h_2": 0.8, "v_9": 1.0})
    assert "Samples present: 2 of 3" in md
    unscored = md.split("## Not scored")[1].split("##")[0]
    assert "v_9" in unscored and "h_1" not in unscored
    lost = md.split("## Models with non-triangle faces")[1].split("##")[0]
    assert "| h_2 | 80.0% | False |" in lost and "| v_9 | 100.0% | not scored |" in lost and "h_1" not in lost


def test_a_model_with_no_triangles_is_a_failed_row_not_a_skipped_sample(tmp_path: Path) -> None:
    """veh_008: its OBJ is all quads, Open3D's reader drops them all, so 05a's pipeline cannot register it; that is a failure of the
    pipeline, scored as such (errors NaN, success False), not a sample left out of the benchmark."""
    d = tmp_path / "veh_9-x"
    d.mkdir()
    (d / "model_veh_9-x.obj").write_text("v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf 1 2 3 4\n")
    (d / "transformation_matrix_veh_9-x.txt").write_text("2 0 0 0\n0 2 0 0\n0 0 2 0\n0 0 0 1\n")
    (d / "pointcloud_veh_9-x_transformed.e57").write_bytes(b"")   # never read: the model fails first
    row = score_sample("PC2Model_v1.4/vehicle/veh_9-x", tmp_path, "unseen", "abc1234")
    assert list(row) == COLUMNS
    assert row["success"] is False and row["seed0_success"] is False and row["scaled"] is True
    assert all(math.isnan(float(str(row[k]))) for k in ("rot_deg", "centroid_m", "scale_err_pct", "est_scale"))

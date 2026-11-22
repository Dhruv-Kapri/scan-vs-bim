import csv
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from scan_vs_bim.benchmark import COLUMNS, gate_agreement, results_markdown, run_benchmark, seen_mark

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
            "seed0_success": str(seed0), "commit": "abc1234"}


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
    md = results_markdown(rows, [], "CMD")
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
    assert "all agree: no" in results_markdown(changed, gate, "CMD")
    assert "all agree: yes" in results_markdown(same, gate, "CMD")

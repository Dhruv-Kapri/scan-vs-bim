import csv
import json
import shutil
from pathlib import Path

import pytest

from run_notebook import run_notebook
from scan_vs_bim.gate import HAND_COLUMNS

ROOT = Path(__file__).parents[1]
NOTEBOOK = ROOT / "notebooks" / "05b_hand_check.ipynb"
SLICE = ROOT / "notebooks" / "01_cras_slice.json"
NEEDS = [ROOT / "data" / "cras" / "cras_voxel_1cm.npz", ROOT / "data" / "cras" / "craslabbim.ifc",
         ROOT / "outputs" / "03a" / "verdicts_no_labels.csv", ROOT / "outputs" / "03a" / "frame.json",
         ROOT / "outputs" / "03b" / "scores_no_labels.csv", ROOT / "outputs" / "03b" / "manifest.json", ROOT / "outputs" / "05a" / "registration.csv"]


def setup_copy(tmp_path):
    """A copy of the notebook with the inputs of the real outputs/ symlinked; its own outputs/05b and hand-check CSV land in tmp_path."""
    (tmp_path / "notebooks").mkdir()
    (tmp_path / "outputs").mkdir()
    (tmp_path / "data").symlink_to(ROOT / "data")
    for d in ("03a", "03b", "05a"):
        (tmp_path / "outputs" / d).symlink_to(ROOT / "outputs" / d)
    shutil.copy(SLICE, tmp_path / "notebooks")
    return Path(shutil.copy(NOTEBOOK, tmp_path / "notebooks"))


def test_notebook_05b_pending_then_scored_from_filled_judgements(tmp_path):
    """Known answers asserted inside 05b (inputs consistent, draw repeatable, expected verdicts follow the tolerance, success flags follow
    the thresholds). Here: a first run writes the 20-row judgement template and 20 close-ups and reports the hand check PENDING; after the
    judgements are filled (3 of 20 disagreeing) a second run keeps the file as it is and scores 17 of 20 = 85 %; the template is never overwritten."""
    for p in NEEDS:
        if not p.exists():
            pytest.skip(f"{p.relative_to(ROOT)} missing (run 03a, 03b, 05a first, see CLAUDE.md)")
    nb = setup_copy(tmp_path)
    run_notebook(nb, timeout=3600)
    hand_csv = tmp_path / "notebooks" / "05b_hand_check.csv"
    rows = list(csv.DictReader(open(hand_csv)))
    assert list(rows[0]) == HAND_COLUMNS and len(rows) == 20 and len({r["global_id"] for r in rows}) == 20
    assert all(r["judgement"] == "" for r in rows) and [int(r["n"]) for r in rows] == list(range(1, 21))
    assert len(list((tmp_path / "outputs" / "05b" / "closeups").glob("*.png"))) == 20
    gate = json.loads((tmp_path / "outputs" / "05b" / "gate.json").read_text())
    assert gate["hand_check"]["status"] == "PENDING" and gate["hand_check"]["n_filled"] == 0
    assert gate["overall"] in ("PENDING", "FAIL")  # never PASS while the hand check is pending

    wrong = {"OK": "shifted", "shifted": "not confirmed", "not confirmed": "OK"}
    for i, r in enumerate(rows):
        r["judgement"] = wrong[r["verdict"]] if i < 3 else r["verdict"]
    with open(hand_csv, "w", newline="") as f:
        w = csv.DictWriter(f, HAND_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    run_notebook(nb, timeout=3600)
    assert list(csv.DictReader(open(hand_csv))) == rows  # the author's entries are untouched
    gate = json.loads((tmp_path / "outputs" / "05b" / "gate.json").read_text())
    assert (gate["hand_check"]["n_filled"], gate["hand_check"]["n_agree"], gate["hand_check"]["status"]) == (20, 17, "PASS")
    assert gate["drawn"] == [r["global_id"] for r in rows]

import csv
import json
import shutil
from pathlib import Path

import pytest

from run_notebook import run_notebook

ROOT = Path(__file__).parents[1]
NOTEBOOK = ROOT / "notebooks" / "03a_compare.ipynb"
SLICE = ROOT / "notebooks" / "01_cras_slice.json"
NEEDS = [ROOT / "data" / "cras" / "cras_voxel_1cm.npz", ROOT / "data" / "cras" / "craslabbim.ifc"]
ELEMENT_CLASSES = {"IfcWallStandardCase", "IfcColumn", "IfcDoor", "IfcWindow", "IfcSlab", "IfcCovering", "IfcStairFlight"}
VERDICTS = {"OK", "shifted", "not confirmed"}  # missing / not visible are unreachable: 01 recovered no scanner positions
COLUMNS = ["global_id", "ifc_class", "verdict", "point_count", "median_signed_offset_mm"]


def test_notebook_03a_writes_per_element_verdicts(tmp_path):
    """Known answers are asserted inside 03a; here: both CSVs (with and without oracle labels) hold one row per room
    element, only element classes, only the three verdicts reachable here (OK, shifted, not confirmed), a zero-point element reads "no points", and the
    top-down PNG is written; the strict and the padded box give the same verdicts (crop_check.csv, issue #23)."""
    for p in NEEDS:
        if not p.exists():
            pytest.skip(f"{p.relative_to(ROOT)} not downloaded (see scripts/fetch_data.py and CLAUDE.md)")
    # Run a copy so the committed notebook is not rewritten and its outputs land in tmp_path, not the real outputs/.
    (tmp_path / "notebooks").mkdir()
    (tmp_path / "outputs").mkdir()
    (tmp_path / "data").symlink_to(ROOT / "data")
    shutil.copy(SLICE, tmp_path / "notebooks")
    copy = shutil.copy(NOTEBOOK, tmp_path / "notebooks")
    run_notebook(Path(copy), timeout=1800)

    out = tmp_path / "outputs" / "03a"
    for variant in ("oracle_labels", "no_labels"):
        with open(out / f"verdicts_{variant}.csv", newline="") as f:
            rows = list(csv.DictReader(f))
        assert list(rows[0])[:len(COLUMNS)] == COLUMNS
        assert "points_past_edge" in rows[0] and all(int(r["points_past_edge"]) >= 0 for r in rows)  # the own-face patch (#20) counts what it leaves out
        assert sum(int(r["points_past_edge"]) for r in rows) > 0  # and it is on: room B has points past the edge of a covering's or a slab's own face
        with open(SLICE) as sf:  # 05b draws by 03a's row order: the patch must not change it (rows follow the slice's element list)
            assert [r["global_id"] for r in rows] == json.load(sf)["room"]["element_global_ids"]
        assert len(rows) == 35 and len({r["global_id"] for r in rows}) == 35
        assert {r["ifc_class"] for r in rows} <= ELEMENT_CLASSES
        assert {r["verdict"] for r in rows} <= VERDICTS
        assert "mostly outside the room box" not in {r["reason"] for r in rows}  # #23: elements are judged on their whole patch, the box only sets scope
        # an element with no points at all says "no points", not "too few points" (issue #19)
        assert all(int(r["point_count"]) > 0 for r in rows if r["reason"] == "too few points")
        assert {r["reason"] for r in rows if r["point_count"] == "0"} <= {"no points"}
    assert (out / "verdicts_top_down.png").stat().st_size > 0

    # #23: the scope taken from the strict box and from the padded box (frozen frame) gives the same verdict for every one of the 35 elements, in both variants
    with open(out / "crop_check.csv", newline="") as f:
        check = list(csv.DictReader(f))
    assert {r["variant"] for r in check} == {"oracle_labels", "no_labels"}
    for variant in ("oracle_labels", "no_labels"):
        rows = [r for r in check if r["variant"] == variant]
        assert len(rows) == 35 and len({r["global_id"] for r in rows}) == 35
        assert all(r["verdict_strict"] in VERDICTS and r["verdict_strict"] == r["verdict_padded"] for r in rows)
        assert all(r["point_count_strict"] == r["point_count_padded"] for r in rows)

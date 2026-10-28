import csv
import shutil
from pathlib import Path

import pytest

from run_notebook import run_notebook

ROOT = Path(__file__).parents[1]
NOTEBOOK = ROOT / "notebooks" / "03a_compare.ipynb"
SLICE = ROOT / "notebooks" / "01_cras_slice.json"
NEEDS = [ROOT / "data" / "cras" / "cras_voxel_1cm.npz", ROOT / "data" / "cras" / "craslabbim.ifc"]
ELEMENT_CLASSES = {"IfcWallStandardCase", "IfcColumn", "IfcDoor", "IfcWindow", "IfcSlab", "IfcCovering", "IfcStairFlight"}
VERDICTS = {"OK", "shifted", "missing", "not visible", "not confirmed"}
COLUMNS = ["global_id", "ifc_class", "verdict", "point_count", "median_signed_offset_mm"]


def test_notebook_03a_writes_per_element_verdicts(tmp_path):
    """Known answers are asserted inside 03a; here: both CSVs (with and without oracle labels) hold one row per room
    element, only element classes, only CONTEXT.md verdicts (no missing / not visible: 01 recovered no scanner
    positions), and the top-down PNG is written."""
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
        assert len(rows) == 35 and len({r["global_id"] for r in rows}) == 35
        assert {r["ifc_class"] for r in rows} <= ELEMENT_CLASSES
        assert {r["verdict"] for r in rows} <= VERDICTS - {"missing", "not visible"}
    assert (out / "verdicts_top_down.png").stat().st_size > 0

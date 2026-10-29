import csv
import json
import shutil
from pathlib import Path

import ifcopenshell
import pytest

from run_notebook import run_notebook

ROOT = Path(__file__).parents[1]
NOTEBOOK = ROOT / "notebooks" / "03b_perturbed.ipynb"
SLICE = ROOT / "notebooks" / "01_cras_slice.json"
IFC = ROOT / "data" / "cras" / "craslabbim.ifc"
NEEDS = [ROOT / "data" / "cras" / "cras_voxel_1cm.npz", IFC]
VERDICTS = {"OK", "shifted", "not confirmed"}  # missing / not visible are unreachable: 01 recovered no scanner positions


def test_notebook_03b_scores_verdicts_against_the_manifest(tmp_path):
    """Known answers are asserted inside 03b; here: the perturbed IFC and its manifest are written, the IFC differs from
    the original only by the manifest's moves (same elements, deletions are scan masks, not IFC changes), and both score
    tables hold an expected and an actual verdict for every perturbed element."""
    for p in NEEDS:
        if not p.exists():
            pytest.skip(f"{p.relative_to(ROOT)} not downloaded (see scripts/fetch_data.py and CLAUDE.md)")
    # Run a copy so the committed notebook is not rewritten and its outputs land in tmp_path, not the real outputs/.
    (tmp_path / "notebooks").mkdir()
    (tmp_path / "outputs").mkdir()
    (tmp_path / "data").symlink_to(ROOT / "data")
    shutil.copy(SLICE, tmp_path / "notebooks")
    copy = shutil.copy(NOTEBOOK, tmp_path / "notebooks")
    run_notebook(Path(copy), timeout=3600)  # nbclient's timeout is per cell, not for the notebook: the slowest cell (ICP against the perturbed model) took minutes on a loaded machine

    out = tmp_path / "outputs" / "03b"
    manifest = json.loads((out / "manifest.json").read_text())
    changes = manifest["changes"]
    moves = [c for c in changes if c["change"] == "moved"]
    masks = [c for c in changes if c["change"] == "not_built"]
    assert sorted(round(sum(v * v for v in c["offset_m"]) ** 0.5, 3) for c in moves) == [0.01, 0.03, 0.10]
    assert len(masks) == 3 and all(c["offset_m"] is None for c in masks)

    original = ifcopenshell.open(str(IFC))
    perturbed = ifcopenshell.open(str(out / "craslabbim_perturbed.ifc"))
    assert {e.GlobalId for e in perturbed.by_type("IfcElement")} == {e.GlobalId for e in original.by_type("IfcElement")}
    assert all(perturbed.by_guid(c["global_id"]) for c in changes)

    perturbed_ids = {c["global_id"] for c in changes}
    for variant in ("oracle_labels", "no_labels"):
        with open(out / f"scores_{variant}.csv", newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 35 and {r["global_id"] for r in rows} >= perturbed_ids
        assert {r["actual"] for r in rows} <= VERDICTS
        assert all(r["expected"] in VERDICTS for r in rows if r["global_id"] in perturbed_ids)

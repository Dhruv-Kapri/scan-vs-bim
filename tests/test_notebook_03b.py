import csv
import json
import shutil
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.placement as ifc_placement
import numpy as np
import pytest

from run_notebook import run_notebook

ROOT = Path(__file__).parents[1]
NOTEBOOK = ROOT / "notebooks" / "03b_perturbed.ipynb"
SLICE = ROOT / "notebooks" / "01_cras_slice.json"
IFC = ROOT / "data" / "cras" / "craslabbim.ifc"
NEEDS = [ROOT / "data" / "cras" / "cras_voxel_1cm.npz", IFC]
VERDICTS = {"OK", "shifted", "not confirmed"}  # missing / not visible are unreachable: 01 recovered no scanner positions


def placements(model):
    return {p.GlobalId: ifc_placement.get_local_placement(p.ObjectPlacement) for p in model.by_type("IfcProduct") if p.ObjectPlacement}


def test_notebook_03b_scores_verdicts_against_the_manifest(tmp_path):
    """Known answers are asserted inside 03b; here: every move has its own perturbed IFC, each differs from the original only by that move (same elements, same
    GUIDs, only the moved wall and the opening elements it carries have a changed placement, each by the manifest's offset), the deletions are scan masks (no IFC), and
    the score tables hold, for each of the six runs, all 35 elements with an expected and an actual verdict on the changed one."""
    for p in NEEDS:
        if not p.exists():
            pytest.skip(f"{p.relative_to(ROOT)} not downloaded (see scripts/fetch_data.py and CLAUDE.md)")
    # Run a copy so the committed notebook is not rewritten and its outputs land in tmp_path, not the real outputs/.
    (tmp_path / "notebooks").mkdir()
    (tmp_path / "outputs").mkdir()
    (tmp_path / "data").symlink_to(ROOT / "data")
    shutil.copy(SLICE, tmp_path / "notebooks")
    copy = shutil.copy(NOTEBOOK, tmp_path / "notebooks")
    run_notebook(Path(copy), timeout=3600)  # nbclient's timeout is per cell, not for the notebook: the slowest cell (ICP against the stress model) took minutes on a loaded machine

    out = tmp_path / "outputs" / "03b"
    manifest = json.loads((out / "manifest.json").read_text())
    changes = manifest["changes"]
    moves = [c for c in changes if c["change"] == "moved"]
    masks = [c for c in changes if c["change"] == "not_built"]
    assert sorted(round(sum(v * v for v in c["offset_m"]) ** 0.5, 3) for c in moves) == [0.01, 0.03, 0.10]
    assert len(masks) == 3 and all(c["offset_m"] is None and c["perturbed_ifc"] is None for c in masks)
    assert len({c["run"] for c in changes}) == 6 and len({c["perturbed_ifc"] for c in moves}) == 3
    assert all(c["expected_verdict"] in VERDICTS for c in changes)

    original = ifcopenshell.open(str(IFC))
    original_ids = {e.GlobalId for e in original.by_type("IfcElement")}
    original_placements = placements(original)
    del original
    for c in moves:  # each move: its own file, and that file differs from the original only by this move
        perturbed = ifcopenshell.open(str(out / Path(c["perturbed_ifc"]).name))
        assert {e.GlobalId for e in perturbed.by_type("IfcElement")} == original_ids
        assert perturbed.by_guid(c["global_id"])
        moved = placements(perturbed)
        changed = {g for g in original_placements if not np.allclose(original_placements[g], moved[g], atol=1e-9)}
        assert set(moved) == set(original_placements)
        assert changed == {c["global_id"], *c["carried"]}, f"{c['run']}: placements changed for {changed - {c['global_id'], *c['carried']}}"
        for g in changed:
            assert np.allclose(moved[g][:3, 3] - original_placements[g][:3, 3], c["offset_m"], atol=1e-6) and np.allclose(moved[g][:3, :3], original_placements[g][:3, :3])
        assert all(np.allclose(original_placements[g], moved[g], atol=1e-9) for g in c["held_in_place"])
        del perturbed

    by_run = {c["run"]: c for c in changes}
    for variant in ("oracle_labels", "no_labels"):
        with open(out / f"scores_{variant}.csv", newline="") as f:
            rows = list(csv.DictReader(f))
        assert {r["run"] for r in rows} == set(by_run)
        for run, c in by_run.items():
            run_rows = [r for r in rows if r["run"] == run]
            assert len(run_rows) == 35 and len({r["global_id"] for r in run_rows}) == 35
            assert {r["actual"] for r in run_rows} <= VERDICTS
            changed_rows = [r for r in run_rows if r["change"]]
            assert [r["global_id"] for r in changed_rows] == [c["global_id"]]
            assert changed_rows[0]["expected"] == c["expected_verdict"] and changed_rows[0]["expected"] in VERDICTS
    with open(out / "occlusion_control.csv", newline="") as f:
        assert len(list(csv.DictReader(f))) == 8  # four configurations, two variants

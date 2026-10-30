import csv
import shutil
from pathlib import Path

import pytest

from run_notebook import run_notebook

ROOT = Path(__file__).parents[1]
NOTEBOOK = ROOT / "notebooks" / "05a_registration_gate.ipynb"
SCALES, GATE = ROOT / "outputs" / "pc2model_scales.csv", ROOT / "outputs" / "05a" / "gate_samples.csv"


def test_notebook_05a_runs_with_known_answers(tmp_path):
    """Known answers asserted inside 05a: the nine samples match the selection rule, T (not inv T) maps each scan onto its
    model, and the criterion line matches the success flags in registration.csv. The gate itself is not asserted: failing is a valid result."""
    needs = [SCALES, GATE]
    if GATE.exists():
        needs += [ROOT / "data" / "pc2model" / Path(r["sample"]).name for r in csv.DictReader(open(GATE))]
    for p in needs:
        if not p.exists():
            pytest.skip(f"{p.relative_to(ROOT)} missing (run scripts/find_scaled_sample.py, scripts/pick_gate_samples.py, then the notebook once to fetch the samples, see CLAUDE.md)")
    # Run a copy so the committed notebook is not rewritten and registration.csv lands in tmp_path, not the real outputs/05a.
    (tmp_path / "notebooks").mkdir()
    (tmp_path / "outputs" / "05a").mkdir(parents=True)
    (tmp_path / "data").symlink_to(ROOT / "data")
    (tmp_path / "outputs" / "pc2model_scales.csv").symlink_to(SCALES)
    shutil.copy(GATE, tmp_path / "outputs" / "05a")
    copy = shutil.copy(NOTEBOOK, tmp_path / "notebooks")
    run_notebook(Path(copy), timeout=3600)
    assert len(list(csv.DictReader(open(tmp_path / "outputs" / "05a" / "registration.csv")))) == 9

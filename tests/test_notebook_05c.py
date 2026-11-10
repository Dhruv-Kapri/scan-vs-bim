import csv
import shutil
from pathlib import Path

import pytest

from run_notebook import run_notebook

ROOT = Path(__file__).parents[1]
NOTEBOOK = ROOT / "notebooks" / "05c_registration_tuning.ipynb"
NEEDS = [ROOT / "data" / "pc2model" / n for n in (
    "fur_010-modelnet", "house_6-sketchfab", "indoor_modelling_5-ISPRS_indoor_modelling-GM",
    "real-indoor_modelling_5-ISPRS_indoor_modelling-GM")]


def test_notebook_05c_runs_with_known_answers(tmp_path: Path) -> None:
    """Known answers asserted inside 05c: the chosen candidate is the plan 05a uses (register.refine_plan). The tuning outcome itself is
    not asserted; here only the table's shape (5 samples x 5 candidates) is. Slow (about 25 min): five samples, five RANSAC seeds each."""
    for p in NEEDS:
        if not any(p.glob("pointcloud_*_transformed.e57")):
            pytest.skip(f"{p.relative_to(ROOT)} missing (run scripts/fetch_data.py, find_scaled_sample.py and fetch_tuning_samples.py, see CLAUDE.md)")
    # Run a copy so the committed notebook is not rewritten and tuning.csv lands in tmp_path, not the real outputs/05c.
    (tmp_path / "notebooks").mkdir()
    (tmp_path / "data").symlink_to(ROOT / "data")
    copy = shutil.copy(NOTEBOOK, tmp_path / "notebooks")
    run_notebook(Path(copy), timeout=7200)
    assert len(list(csv.DictReader(open(tmp_path / "outputs" / "05c" / "tuning.csv")))) == 25

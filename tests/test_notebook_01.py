import shutil
from pathlib import Path

import pytest

from run_notebook import run_notebook

ROOT = Path(__file__).parents[1]
NOTEBOOK = ROOT / "notebooks" / "01_data.ipynb"
NEEDS = [ROOT / "data" / "cras" / "cras_voxel_1cm.npz", ROOT / "data" / "cras" / "craslabbim.ifc"]


def test_notebook_01_runs_with_known_answers(tmp_path):
    """Known answers are asserted inside 01: the synthetic hole detector recovers its holes, the CRAS scan is far off the model's frame and the estimated transform fixes it, the room box holds walls, a door and windows, UVigo scale is 1."""
    for p in NEEDS:
        if not p.exists():
            pytest.skip(f"{p.relative_to(ROOT)} not downloaded (see scripts/fetch_data.py and CLAUDE.md)")
    # Run a copy so the committed 01_cras_slice.json is not rewritten (ICP drifts by fractions of a mm per run).
    (tmp_path / "notebooks").mkdir()
    (tmp_path / "data").symlink_to(ROOT / "data")
    copy = shutil.copy(NOTEBOOK, tmp_path / "notebooks")
    run_notebook(Path(copy), timeout=1800)
    assert (tmp_path / "notebooks" / "01_cras_slice.json").exists()

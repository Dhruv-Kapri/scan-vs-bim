import shutil
from pathlib import Path

import pytest

from run_notebook import run_notebook

ROOT = Path(__file__).parents[1]
NOTEBOOK = ROOT / "notebooks" / "02_align.ipynb"
NEEDS = [
    ROOT / "outputs" / "pc2model_scales.csv",
    ROOT / "data" / "pc2model" / "real-indoor_modelling_3-ISPRS_indoor_modelling-UVigo",
    ROOT / "data" / "pc2model" / "fur_010-modelnet",
]


def test_notebook_02_runs_with_known_answers(tmp_path):
    """Known answers are asserted inside 02: the scaled sample is fur_010, T beats inv(T) on UVigo, the best UVigo draw is within the rotation gate, the rigid baseline fails on fur_010, the scale estimate is within 5%."""
    for p in NEEDS:
        if not p.exists():
            pytest.skip(f"{p.relative_to(ROOT)} missing (run scripts/find_scaled_sample.py and scripts/fetch_data.py, see CLAUDE.md)")
    # Run a copy so the committed notebook is not rewritten and its PNGs land in tmp_path, not the real outputs/02.
    (tmp_path / "notebooks").mkdir()
    (tmp_path / "outputs").mkdir()
    (tmp_path / "data").symlink_to(ROOT / "data")
    (tmp_path / "outputs" / "pc2model_scales.csv").symlink_to(NEEDS[0])
    copy = shutil.copy(NOTEBOOK, tmp_path / "notebooks")
    run_notebook(Path(copy), timeout=1800)

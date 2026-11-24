import shutil
from pathlib import Path

import pytest

from run_notebook import run_notebook

ROOT = Path(__file__).parents[1]
NOTEBOOK = ROOT / "notebooks" / "01_data.ipynb"
COMMITTED_SLICE = ROOT / "notebooks" / "01_cras_slice.json"
NEEDS = [ROOT / "data" / "cras" / "cras_voxel_1cm.npz", ROOT / "data" / "cras" / "craslabbim.ifc"]


def test_notebook_01_runs_with_known_answers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Known answers are asserted inside 01: the synthetic hole detector recovers its holes, the CRAS scan is far off the model's frame and the estimated transform fixes it, the room box holds walls, a door and windows, UVigo scale is 1. Its last cell checks the run against the committed 01_cras_slice.json within slice_parity's tolerances (registration drifts run to run, #50) and, without WRITE_SLICE=1, leaves that file alone."""
    for p in NEEDS:
        if not p.exists():
            pytest.skip(f"{p.relative_to(ROOT)} not downloaded (see scripts/fetch_data.py and CLAUDE.md)")
    # Run a copy in tmp_path with the committed slice beside it: the notebook's parity assert is the drift check, and it must not rewrite the copy.
    monkeypatch.delenv("WRITE_SLICE", raising=False)
    (tmp_path / "notebooks").mkdir()
    (tmp_path / "data").symlink_to(ROOT / "data")
    copy = shutil.copy(NOTEBOOK, tmp_path / "notebooks")
    committed = shutil.copy(COMMITTED_SLICE, tmp_path / "notebooks")
    run_notebook(Path(copy), timeout=1800)
    assert Path(committed).read_bytes() == COMMITTED_SLICE.read_bytes()
    assert (tmp_path / "outputs" / "01" / "01_cras_slice.json").exists()

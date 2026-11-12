import shutil
from pathlib import Path

import nbformat
import pytest

from run_notebook import run_notebook

ROOT = Path(__file__).parents[1]
NOTEBOOK = ROOT / "notebooks" / "03c_tuning_room.ipynb"
NEEDS = [ROOT / "data" / "cras" / "cras_voxel_1cm.npz", ROOT / "data" / "cras" / "craslabbim.ifc",
         ROOT / "outputs" / "03a" / "verdicts_no_labels.csv", ROOT / "outputs" / "03a" / "verdicts_oracle_labels.csv"]


def test_03c_copy_of_03a_logic_reproduces_03a_on_room_b(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """03c imports 03a's logic from scan_vs_bim.compare (it carried a copy until #41). Run on room B (SLICE_JSON=01_cras_slice.json), up to and including its room-B check cell,
    03c's use of it (the assignment on the 135 elements, the own-face patch cut by `recut`, its row adapter) must give 03a's verdicts, point counts and medians row for row:
    the check is asserted inside the notebook. Needs outputs/03a (run 03a first)."""
    for p in NEEDS:
        if not p.exists():
            pytest.skip(f"{p.relative_to(ROOT)} not present (fetch the data, run 03a)")
    (tmp_path / "notebooks").mkdir()
    (tmp_path / "outputs").mkdir()
    (tmp_path / "data").symlink_to(ROOT / "data")
    shutil.copytree(ROOT / "outputs" / "03a", tmp_path / "outputs" / "03a")
    shutil.copy(ROOT / "notebooks" / "01_cras_slice.json", tmp_path / "notebooks")
    nb = nbformat.read(NOTEBOOK, as_version=4)
    last = max(i for i, c in enumerate(nb.cells) if c.cell_type == "code" and "room-B check" in c.source)
    nb.cells = nb.cells[:last + 1]
    path = tmp_path / "notebooks" / NOTEBOOK.name
    nbformat.write(nb, path)
    monkeypatch.setenv("SLICE_JSON", "01_cras_slice.json")
    run_notebook(path, timeout=3600)

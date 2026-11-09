from pathlib import Path

import nbformat
import pytest
from nbclient.exceptions import CellExecutionError

from run_notebook import run_notebook


def make_nb(path: Path, *sources: str) -> Path:
    nb = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(s) for s in sources])
    nbformat.write(nb, path)
    return path


def test_runs_in_the_notebook_dir_and_a_failing_cell_raises(tmp_path: Path) -> None:
    (tmp_path / "x.txt").write_text("hi")
    nb = make_nb(tmp_path / "nb.ipynb", "assert open('x.txt').read() == 'hi'", "raise ValueError('boom')")
    # The match on "boom" proves the first cell passed (a wrong cwd would raise FileNotFoundError in cell 1 instead); one kernel start instead of two.
    with pytest.raises(CellExecutionError, match="boom"):
        run_notebook(nb)

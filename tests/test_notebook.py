import nbformat
import pytest
from nbclient.exceptions import CellExecutionError

from run_notebook import run_notebook


def make_nb(path, *sources):
    nb = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(s) for s in sources])
    nbformat.write(nb, path)
    return path


def test_runs_passing_notebook(tmp_path):
    (tmp_path / "x.txt").write_text("hi")
    run_notebook(make_nb(tmp_path / "ok.ipynb", "x = 1", "assert x == 1 and open('x.txt').read() == 'hi'"))  # cwd = notebook dir


def test_failing_cell_raises(tmp_path):
    with pytest.raises(CellExecutionError):
        run_notebook(make_nb(tmp_path / "bad.ipynb", "x = 1", "raise ValueError('boom')"))

from pathlib import Path

from run_notebook import run_notebook

NOTEBOOK = Path(__file__).parents[1] / "notebooks" / "00_pipeline_overview.ipynb"


def test_notebook_00_runs_with_known_answers():
    """The known answers (registration within the 05 gate, moved wall shifted, rest OK, BCF issue) are asserted inside 00."""
    run_notebook(NOTEBOOK)

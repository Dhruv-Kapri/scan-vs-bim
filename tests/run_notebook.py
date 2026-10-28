from pathlib import Path

import nbformat
from nbclient import NotebookClient


def run_notebook(path: Path, timeout: int = 600) -> None:
    """Execute a notebook top to bottom in its own directory; nbclient raises CellExecutionError on any cell error."""
    nb = nbformat.read(path, as_version=4)
    NotebookClient(nb, timeout=timeout, kernel_name="python3", resources={"metadata": {"path": str(Path(path).parent)}}).execute()

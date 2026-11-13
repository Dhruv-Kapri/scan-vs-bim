"""The notebooks' CSV tables (03a's verdicts, 03b's scores, 05a's registration) read back as rows of text."""

import csv
from pathlib import Path


def read_rows(path: Path) -> list[dict[str, str]]:
    """The rows of a CSV file with a header, in file order, every value as written (a blank field is ""); the caller parses numbers."""
    with open(path, newline="") as f:
        return list(csv.DictReader(f))

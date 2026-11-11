import tomllib
from pathlib import Path

from mypy import api

ROOT: Path = Path(__file__).parents[1]


def test_mypy_as_configured_is_clean_and_covers_scripts() -> None:
    """`uv run mypy` with no paths checks what pyproject.toml's `files` lists; that must include scripts/ and be clean."""
    files: list[str] = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["mypy"]["files"]
    assert "scripts" in files, f"[tool.mypy] files = {files} leaves scripts/ unchecked"
    # --config-file makes the run independent of the current directory.
    stdout, stderr, status = api.run(["--config-file", str(ROOT / "pyproject.toml")] + [str(ROOT / f) for f in files])
    assert status == 0, f"mypy exit {status}:\n{stdout}{stderr}"

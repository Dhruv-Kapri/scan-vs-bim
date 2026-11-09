import json
import shutil
from pathlib import Path

import pytest

from run_notebook import run_notebook

ROOT = Path(__file__).parents[1]
NOTEBOOK = ROOT / "notebooks" / "03d_floor_ramp.ipynb"
NEEDS = [ROOT / "data" / "cras" / "cras_voxel_1cm.npz", ROOT / "data" / "cras" / "craslabbim.ifc", ROOT / "outputs" / "03a" / "frame.json"]
KEYS = {"floor", "ceiling", "height", "subsets", "residual_correlation", "wall_lean", "n_cells", "ceiling_levels", "floor_z"}


def test_notebook_03d_writes_the_gradients_and_their_intervals(tmp_path: Path) -> None:
    """The notebook asserts its known answers (a rotated and a floor-sloped synthetic room) itself; here: it runs on the real cache with 03a's frame,
    and writes summary.json with the floor, ceiling and room-height gradients (each with an interval that holds the estimate), the correlation and the wall-lean fit, and the figures."""
    for p in NEEDS:
        if not p.exists():
            pytest.skip(f"{p.relative_to(ROOT)} not found (see scripts/fetch_data.py, CLAUDE.md, and run notebook 03a first)")
    # Run a copy so the committed notebook is not rewritten and its outputs land in tmp_path, not the real outputs/.
    (tmp_path / "notebooks").mkdir()
    (tmp_path / "outputs").mkdir()
    (tmp_path / "data").symlink_to(ROOT / "data")
    shutil.copytree(ROOT / "outputs" / "03a", tmp_path / "outputs" / "03a")
    copy = shutil.copy(NOTEBOOK, tmp_path / "notebooks")
    run_notebook(Path(copy), timeout=1800)

    out = tmp_path / "outputs" / "03d"
    summary = json.loads((out / "summary.json").read_text())
    assert KEYS <= set(summary)
    assert abs(summary["floor_z"] - 0.100) < 1e-6 and len(summary["ceiling_levels"]) >= 2 and summary["n_cells"] >= 100
    for surface in ("floor", "ceiling", "height"):
        s = summary[surface]
        for g in ("gx", "gy"):
            lo, hi = s[f"{g}_ci"]
            assert lo <= s[g] <= hi
    assert -1 <= summary["residual_correlation"]["r"] <= 1 and summary["wall_lean"]["n_faces"] >= 8
    for png in ("cells_map.png", "gradients.png", "wall_lean.png"):
        assert (out / png).stat().st_size > 0

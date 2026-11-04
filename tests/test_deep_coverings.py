import json
from pathlib import Path

import numpy as np
import pytest

from scan_vs_bim.compare import _unit_normals
from scan_vs_bim.load import load_ifc_elements

ROOT: Path = Path(__file__).parents[1]
IFC: Path = ROOT / "data" / "cras" / "craslabbim.ifc"
ROOM_B: Path = ROOT / "notebooks" / "01_cras_slice.json"
HELD_OUT: list[Path] = [ROOT / "notebooks" / "03c_tuning_slice.json", ROOT / "notebooks" / "03c_tuning_slice_room_a.json"]
FORROS_1: str = "33gtcvddH7cec8$WOT4fKs"
SIDE_FACE: float = 0.99  # |n_z| <= this: a side face, not one of the two faces across z
DEEP: float = 0.15  # m: the z-span of a side face above which a slab or covering counts as deep


def _slab_and_covering_guids(slice_json: Path) -> set[str]:
    elements = json.loads(slice_json.read_text())["room"]["elements"]
    return {e["global_id"] for e in elements if e["ifc_class"] in ("IfcSlab", "IfcCovering")}


def test_forros_1_is_the_only_deep_slab_or_covering_in_the_three_rooms() -> None:
    """Pins the premise of issue #32 (keep the own-face rule: a slab's or covering's own face is only its faces across z).
    Among the IfcSlab and IfcCovering elements listed in room B and the two 03c rooms (west hall, room A), only the covering
    Forros 1 has a side face (|n_z| <= 0.99) spanning more than 15 cm in z, and it is in room B's list only. If this fails,
    the slices or the IFC changed: revisit #32 on the held-out rooms under #20's rule (a deep-side-face rule may now be testable)."""
    if not IFC.exists():
        pytest.skip(f"{IFC.relative_to(ROOT)} not downloaded (see scripts/fetch_data.py and CLAUDE.md)")
    room_b = _slab_and_covering_guids(ROOM_B)
    held_out: set[str] = set().union(*(_slab_and_covering_guids(p) for p in HELD_OUT))
    meshes = load_ifc_elements(IFC, only_guids=sorted(room_b | held_out))

    deep: set[str] = set()
    for m in meshes:
        side = np.abs(_unit_normals(m.vertices, m.faces)[:, 2]) <= SIDE_FACE
        z = m.vertices[m.faces][side][:, :, 2]  # (triangles, 3 corners)
        if side.any() and (z.max(axis=1) - z.min(axis=1)).max() > DEEP:
            deep.add(m.global_id)

    assert deep == {FORROS_1}
    assert FORROS_1 in room_b
    assert FORROS_1 not in held_out

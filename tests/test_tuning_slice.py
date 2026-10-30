import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
ROOM_B = json.loads((ROOT / "notebooks" / "01_cras_slice.json").read_text())
HALL = ROOT / "notebooks" / "03c_tuning_slice.json"  # written by scripts/make_tuning_slice.py
ROOM_A = ROOT / "notebooks" / "03c_tuning_slice_room_a.json"
SHARED_WALL = "Drywall:961571"  # room A and room B's common wall (hand-check element 6)
IN_B = {e["global_id"] for e in ROOM_B["room"]["elements"]}


def overlap_xy(a, b):
    """Area (m2) of the plan-view overlap of two boxes given as dicts with xmin..ymax."""
    dx = min(a["xmax"], b["xmax"]) - max(a["xmin"], b["xmin"])
    dy = min(a["ymax"], b["ymax"]) - max(a["ymin"], b["ymin"])
    return max(dx, 0) * max(dy, 0)


@pytest.mark.parametrize("path", [HALL, ROOM_A], ids=["west hall", "room A"])
def test_tuning_slice_has_the_schema_03a_reads(path):
    s = json.loads(path.read_text())
    assert set(s) >= {"frame", "room", "scanner_positions", "scoring_exclusions"}
    assert s["frame"]["scan_to_model_4x4"] == ROOM_B["frame"]["scan_to_model_4x4"]  # the lab's recorded transform, reused as it is
    room = s["room"]
    assert set(room) >= {"box_model_frame", "scan_points_in_box", "element_global_ids", "elements", "element_classes"}
    assert room["element_global_ids"] == [e["global_id"] for e in room["elements"]]
    assert len(set(room["element_global_ids"])) == len(room["element_global_ids"])
    assert all(set(e) == {"global_id", "ifc_class", "name", "inside_box"} for e in room["elements"])
    assert s["scanner_positions"]["recovered"] is False


@pytest.mark.parametrize("path", [HALL, ROOM_A], ids=["west hall", "room A"])
def test_every_element_in_room_b_s_list_is_excluded_from_scoring_and_listed(path):
    """Elements that room B (the gate's slice) also lists are kept in the room (their points must be assigned to something) but never scored or tuned on."""
    s = json.loads(path.read_text())
    shared = {e["global_id"] for e in s["room"]["elements"] if e["global_id"] in IN_B}
    assert {e["global_id"] for e in s["scoring_exclusions"]} == shared
    assert [e["global_id"] for e in s["provenance"]["elements_also_in_room_B"]] == sorted(shared)
    assert all(e["reason"] for e in s["scoring_exclusions"])


def test_west_hall_is_held_out_from_room_b():
    """No overlap with room B's box; the only shared elements are the building-wide slab and covering."""
    s = json.loads(HALL.read_text())
    assert overlap_xy(s["room"]["box_model_frame"], ROOM_B["room"]["box_model_frame"]) == 0
    assert {e["ifc_class"] for e in s["scoring_exclusions"]} <= {"IfcSlab", "IfcCovering"}


def test_room_a_overlaps_room_b_only_by_the_shared_wall_and_excludes_it_by_name():
    """Room A's box overlaps room B's only by the shared wall's thickness (a strip under 0.15 m deep), and that wall is excluded from scoring with its own reason; the other excluded
    elements are the ones room B's list also holds (building-wide slab, coverings and east wall, B's west walls, the windows on the boundary strip)."""
    s = json.loads(ROOM_A.read_text())
    a, b = s["room"]["box_model_frame"], ROOM_B["room"]["box_model_frame"]
    assert overlap_xy(a, b) < 0.15 * (a["xmax"] - a["xmin"])
    shared_wall = [e for e in s["scoring_exclusions"] if e["name"].endswith(SHARED_WALL)]
    assert len(shared_wall) == 1 and "shared" in shared_wall[0]["reason"]
    assert shared_wall[0]["global_id"] in {e["global_id"] for e in s["room"]["elements"]}  # kept in the room: the points on its room-A face must be assigned to it

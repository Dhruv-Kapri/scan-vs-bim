import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
ROOM_B = json.loads((ROOT / "notebooks" / "01_cras_slice.json").read_text())
SLICE = ROOT / "notebooks" / "03c_tuning_slice.json"  # written by scripts/make_tuning_slice.py


def overlap_xy(a, b):
    """Area (m2) of the plan-view overlap of two boxes given as dicts with xmin..ymax."""
    dx = min(a["xmax"], b["xmax"]) - max(a["xmin"], b["xmin"])
    dy = min(a["ymax"], b["ymax"]) - max(a["ymin"], b["ymin"])
    return max(dx, 0) * max(dy, 0)


def test_tuning_slice_has_the_schema_03a_reads():
    s = json.loads(SLICE.read_text())
    assert set(s) >= {"frame", "room", "scanner_positions"}
    assert s["frame"]["scan_to_model_4x4"] == ROOM_B["frame"]["scan_to_model_4x4"]  # the lab's recorded transform, reused as it is
    room = s["room"]
    assert set(room) >= {"box_model_frame", "scan_points_in_box", "element_global_ids", "elements", "element_classes"}
    assert room["element_global_ids"] == [e["global_id"] for e in room["elements"]]
    assert len(set(room["element_global_ids"])) == len(room["element_global_ids"])
    assert all(set(e) == {"global_id", "ifc_class", "name", "inside_box"} for e in room["elements"])
    assert s["scanner_positions"]["recovered"] is False


def test_tuning_room_is_held_out_from_room_b():
    """The tuning room must not overlap room B's box and share no wall, window or door with room B. The only shared elements are
    the building-wide slab and covering, which run through both rooms, and the slice records them."""
    s = json.loads(SLICE.read_text())
    assert overlap_xy(s["room"]["box_model_frame"], ROOM_B["room"]["box_model_frame"]) == 0
    in_b = {e["global_id"] for e in ROOM_B["room"]["elements"]}
    shared = [e for e in s["room"]["elements"] if e["global_id"] in in_b]
    assert {e["ifc_class"] for e in shared} <= {"IfcSlab", "IfcCovering"}
    assert [e["global_id"] for e in s["provenance"]["elements_also_in_room_B"]] == [e["global_id"] for e in sorted(shared, key=lambda e: e["global_id"])]

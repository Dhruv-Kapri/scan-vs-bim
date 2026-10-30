"""Write the held-out CRAS rooms that 03a's method is tuned on (issue #20): notebooks/03c_tuning_slice.json (west hall) and 03c_tuning_slice_room_a.json.

Room B (notebook 01) is the Phase 0.5 gate's own slice, so the method is tuned on another room of the lab and room B
is only re-run afterwards. The tuning room is the SOUTH PART OF THE WEST HALL: it shares no wall (and no box face) with
room B, which sits on the other side of the central lobby. The IFC has no IfcSpace, so, as in 01, a room is a box in
the model frame: bounded by IFC walls on the west, south and east; the north face is a cut through the open hall at the
y where it crosses the fewest walls, windows and columns (chosen below, not by eye). An element belongs to the room if
its bounding box touches the box (01's rule); `inside_box` says whether it lies wholly inside.

Room A (added in phase 2 of #20, owner's decision) is the room south of room B and shares B's south wall `Drywall:961571` (hand-check element 6). It is a
second tuning slice with scoring exclusions: every element that is in room B's element list (that wall, and the building-wide floor slab and ceiling coverings that run through
both rooms) is kept in the room (the points near it must be assigned to something) but is **not scored or tuned on**; `scoring_exclusions` in the JSON lists them. The same
exclusion is recorded for the west hall, whose list shares the floor slab and one ceiling covering with room B.

Same schema as 01_cras_slice.json (03a reads `frame`, `room`, `scanner_positions`); the frame is 01's recorded transform,
copied unchanged. Usage: uv run python scripts/make_tuning_slice.py   (about 5-10 minutes: tessellates the lab's elements)
"""

import json
from pathlib import Path

import ifcopenshell
import numpy as np

from scan_vs_bim.load import load_ifc_elements

ROOT = Path(__file__).resolve().parent.parent
IFC = ROOT / "data" / "cras" / "craslabbim.ifc"
CACHE = ROOT / "data" / "cras" / "cras_voxel_1cm.npz"
ROOM_B_JSON = ROOT / "notebooks" / "01_cras_slice.json"

ELEMENT_CLASSES = ("IfcWallStandardCase", "IfcColumn", "IfcDoor", "IfcWindow", "IfcSlab", "IfcCovering", "IfcStairFlight")  # 01's list
# Fixed by looking at the registered plan (scan + model section): the hall's west wall is a 30 cm wall at x -9.92 to -9.62, its south
# wall y -0.94 to -0.79, its east side is 10 cm drywall at x -2.81 to -2.71. Faces 1 cm outside the walls' outer faces, as 01 does for room B.
ROOMS = {  # JSON file -> room. ymax None: the north cut is searched (pick_ymax). Faces 1 cm outside the walls' outer faces, as 01 does for room B.
    "03c_tuning_slice.json": dict(name="south part of the west hall", box=dict(xmin=-9.93, xmax=-2.70, ymin=-0.95, zmin=-0.10, zmax=3.05, ymax=None),
                                  why="held out from room B (the gate's slice): no shared wall, no shared box face; rooms A and C each share a wall with room B (A its south wall, C its north wall)"),
    # Room A: x as room B (0.38 to 8.30); south: the outer wall `...919855` at y -4.31 to -4.16 (box 1 cm outside); north y 2.92: the shared wall `Drywall:961571` (y 2.91 to 3.01) touches the box, so its A-side
    # face (y 2.91) is assigned to it and not to a neighbour; the box overlaps room B's box (y from 2.90) by 2 cm, the shared wall's thickness.
    "03c_tuning_slice_room_a.json": dict(name="room A (south of room B)", box=dict(xmin=0.38, xmax=8.30, ymin=-4.32, zmin=-0.10, zmax=3.05, ymax=2.92),
                                         why="second tuning slice (owner's decision, #20 phase 2): same drywall style as room B; shares room B's south wall `Drywall:961571` (hand-check element 6), which is excluded from scoring and tuning"),
}
YMAX_SEARCH = np.arange(8.0, 10.51, 0.05)  # where the north cut may go: the hall's middle, so the room is about as big as room B (8 x 8 m)
SPANNING = ("IfcSlab", "IfcCovering")  # run the length of the hall whatever the cut; not counted as straddling it


def touches(lo, hi, box_lo, box_hi):
    return ((lo < box_hi) & (hi > box_lo)).all(1)


def pick_ymax(box, lo, hi, classes, names):
    """The north cut y with the fewest straddling elements (a wall, window, door or column that the cut passes through)."""
    in_x = (lo[:, 0] < box["xmax"]) & (hi[:, 0] > box["xmin"])
    movable = np.array([c not in SPANNING for c in classes])
    best = None
    for y in YMAX_SEARCH:
        straddle = in_x & movable & (lo[:, 1] < y) & (hi[:, 1] > y) & (lo[:, 2] < box["zmax"]) & (hi[:, 2] > box["zmin"])
        # walls that run along y (the hall's west wall and similar) straddle every cut; only count the ones the cut slices through the middle of
        short = straddle & ((hi[:, 1] - lo[:, 1]) < 5.0)
        n = int(short.sum())
        if best is None or n < best[1]:
            best = (float(round(y, 2)), n, [names[i] for i in np.flatnonzero(short)])
    return best


def build(room, els, lo, hi, classes, name_of, room_b, T, xyz):
    box = dict(room["box"])
    if box["ymax"] is None:
        ymax, n_straddle, straddlers = pick_ymax(box, lo, hi, classes, [name_of[e.global_id] for e in els])
        box["ymax"] = ymax
        north_cut = {"ymax": ymax, "walls_windows_columns_cut_through": n_straddle, "which": straddlers}
    else:
        north_cut = {"ymax": box["ymax"], "fixed": True}
    box_lo = np.array([box[k] for k in ("xmin", "ymin", "zmin")])
    box_hi = np.array([box[k] for k in ("xmax", "ymax", "zmax")])
    touch = touches(lo, hi, box_lo, box_hi)
    inside = ((lo >= box_lo - 1e-3) & (hi <= box_hi + 1e-3)).all(1)
    listing = [dict(global_id=e.global_id, ifc_class=e.ifc_class, name=name_of[e.global_id], inside_box=bool(inside[i]))
               for i, e in sorted(enumerate(els), key=lambda t: (t[1].ifc_class, t[1].global_id)) if touch[i]]
    n_in = 0
    for i in range(0, len(xyz), 4_000_000):
        p = xyz[i:i + 4_000_000]
        q = p @ T[:3, :3].T.astype(np.float32) + T[:3, 3].astype(np.float32)
        n_in += int(((q >= box_lo) & (q <= box_hi)).all(1).sum())
    b = room_b["room"]["box_model_frame"]
    in_b = {e["global_id"] for e in room_b["room"]["elements"]}
    shared = [e for e in listing if e["global_id"] in in_b]
    overlap = max(min(box["xmax"], b["xmax"]) - max(box["xmin"], b["xmin"]), 0) * max(min(box["ymax"], b["ymax"]) - max(box["ymin"], b["ymin"]), 0)
    classes_in = [e["ifc_class"] for e in listing]
    exclusions = [dict(global_id=e["global_id"], name=e["name"], ifc_class=e["ifc_class"],
                       reason=("the wall room B and this room share (hand-check element 6 in room B)" if e["name"].endswith("Drywall:961571") else "in room B's element list (the gate's slice)"))
                  for e in shared]
    out = {
        "frame": room_b["frame"],  # 01's recorded transform, reused unchanged (it is the lab's, not room B's)
        "room": {
            "box_model_frame": box,
            "frame_note": "model frame; apply frame.scan_to_model_4x4 to scan points before cropping",
            "scan_points_in_box": n_in,
            "element_global_ids": [e["global_id"] for e in listing],
            "elements": listing,
            "element_classes": {c: classes_in.count(c) for c in sorted(set(classes_in))},
        },
        "scanner_positions": room_b["scanner_positions"],
        "scoring_exclusions": exclusions,  # kept in the room, never scored or tuned on
        "provenance": {
            "script": "scripts/make_tuning_slice.py",
            "room": room["name"],
            "why": room["why"],
            "north_cut": north_cut,
            "plan_overlap_with_room_B_m2": overlap,
            "elements_also_in_room_B": [{"global_id": e["global_id"], "name": e["name"]} for e in shared],
        },
    }
    return out, len(listing), int(inside[touch].sum())


def main():
    model = ifcopenshell.open(str(IFC))
    guids = [e.GlobalId for c in ELEMENT_CLASSES for e in model.by_type(c)]
    name_of = {e.GlobalId: str(e.Name) for c in ELEMENT_CLASSES for e in model.by_type(c)}
    els = load_ifc_elements(IFC, only_guids=guids)
    lo, hi = np.array([e.vertices.min(0) for e in els]), np.array([e.vertices.max(0) for e in els])
    classes = [e.ifc_class for e in els]
    room_b = json.loads(ROOM_B_JSON.read_text())
    T = np.array(room_b["frame"]["scan_to_model_4x4"])
    xyz = np.load(CACHE)["xyz"]
    for fname, room in ROOMS.items():
        out, n_el, n_inside = build(room, els, lo, hi, classes, name_of, room_b, T, xyz)
        (ROOT / "notebooks" / fname).write_text(json.dumps(out, indent=1))
        print(f"{fname}: {room['name']}: box {out['room']['box_model_frame']}, {n_el} elements ({n_inside} inside): {out['room']['element_classes']}, "
              f"{out['room']['scan_points_in_box']:,} scan points; plan overlap with room B {out['provenance']['plan_overlap_with_room_B_m2']:.2f} m2; "
              f"excluded from scoring ({len(out['scoring_exclusions'])}): {[e['name'][-22:] for e in out['scoring_exclusions']]}")


if __name__ == "__main__":
    main()

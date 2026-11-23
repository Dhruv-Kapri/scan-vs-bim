"""Parity check of notebook 01's slice (01_cras_slice.json) against a re-run (#50): pure functions over JSON-like trees.

01's registration drifts from run to run with the same seeds (about 1e-4 m on the translation, 5e-4 / 7e-4 degrees on yaw / tilt,
the 5th significant digit of the distance statistics, up to +-600 of 3.67 M scan points in the room box). Pinning Open3D to one
thread (o3d.utility.set_max_threads(1)) does not stop it: two such runs, 2026-11-23, differed by 2.8e-4 m and 1.3e-3 degrees,
1.0e-4 m on the p90 distance, 367 room-box points, and the scanner position by one 2 cm floor-map cell. The tolerances below
are 3x (translation, room-box points) to 10x the largest drift seen, and 1 mm is well under USIBD LOA30's 15 mm, so drift within
them is run-to-run noise, not a changed result. Every field without a tolerance must match exactly."""

from collections.abc import Mapping
from typing import Any, TypeGuard

_DISTANCE_KEYS = ("as delivered", "translation only", "translation + ICP")

# dotted path -> absolute tolerance, in the unit of the field
SLICE_TOLERANCES: dict[str, float] = {
    "frame.scan_to_model_4x4": 1e-3,  # elementwise: 1 mm on the translation column (m), ~0.06 degrees on the rotation entries
    "frame.translation_m": 1e-3,  # m
    "frame.yaw_deg": 0.01,  # degrees
    "frame.tilt_deg": 0.01,  # degrees
    # m; the same 1 mm as the translation, as these are measured through the transform (p90 moved 0.10 mm between two runs)
    **{f"frame.median_distance_m.{k}": 1e-3 for k in _DISTANCE_KEYS},
    **{f"frame.p90_distance_m.{k}": 1e-3 for k in _DISTANCE_KEYS},
    "room.scan_points_in_box": 2000,  # points; the box edge cuts a registered cloud that moves by fractions of a mm
    "uvigo.median_distance_after_ground_truth_m": 1e-4,  # m
    # m; the hole detector snaps to 2 cm floor-map cells, so sub-mm drift can move a position by one cell (17.009 vs 16.989 m
    # seen); one cell plus the 1 mm rounding, well inside 01's own 5 cm known-answer check of the detector
    "scanner_positions.positions_model_frame": 0.025,
    "scanner_positions.positions_scan_frame": 0.025,
}


def _is_number(x: object) -> TypeGuard[int | float]:
    return isinstance(x, int | float) and not isinstance(x, bool)


def _close(c: object, r: object, path: str, tol: float, out: list[str]) -> None:
    """Numbers (or equally shaped nested lists of numbers) within `tol`, elementwise."""
    if isinstance(c, list) and isinstance(r, list) and len(c) == len(r):
        for i, (a, b) in enumerate(zip(c, r, strict=True)):
            _close(a, b, f"{path}[{i}]", tol, out)
    elif _is_number(c) and _is_number(r):
        if abs(c - r) > tol:
            out.append(f"{path}: committed {c!r}, re-run {r!r}, differ by {abs(c - r):.3g} > tolerance {tol:g}")
    else:
        out.append(f"{path}: committed {c!r}, re-run {r!r}, shapes or types differ (tolerance {tol:g})")


def _walk(c: object, r: object, path: str, out: list[str]) -> None:
    if path in SLICE_TOLERANCES:
        _close(c, r, path, SLICE_TOLERANCES[path], out)
    elif isinstance(c, dict) and isinstance(r, dict):
        for k in c.keys() | r.keys():
            sub = f"{path}.{k}" if path else str(k)
            if k not in r:
                out.append(f"{sub}: in the committed slice, missing from the re-run (exact)")
            elif k not in c:
                out.append(f"{sub}: in the re-run, missing from the committed slice (exact)")
            else:
                _walk(c[k], r[k], sub, out)
    elif isinstance(c, list) and isinstance(r, list):
        if len(c) != len(r):
            out.append(f"{path}: committed list has {len(c)} items, re-run {len(r)} (exact)")
        else:
            for i, (a, b) in enumerate(zip(c, r, strict=True)):
                _walk(a, b, f"{path}[{i}]", out)
    elif c != r or (type(c) is not type(r) and not (_is_number(c) and _is_number(r))):
        out.append(f"{path}: committed {c!r}, re-run {r!r} (exact)")


def slice_mismatches(committed: Mapping[str, Any], rerun: Mapping[str, Any]) -> list[str]:
    """One message per difference between two slices; empty = parity. Paths in SLICE_TOLERANCES may differ by at most that much, all else exactly."""
    out: list[str] = []
    _walk(dict(committed), dict(rerun), "", out)
    return sorted(out)


def _numbers(x: object) -> list[float]:
    return [v for item in x for v in _numbers(item)] if isinstance(x, list) else [float(x)]  # type: ignore[arg-type]


def _at(tree: Mapping[str, Any], path: str) -> object:
    node: Any = tree
    for key in path.split("."):
        node = node[key]
    return node


def max_abs_drift(committed: Mapping[str, Any], rerun: Mapping[str, Any], path: str) -> float:
    """The largest absolute difference between the two slices at one dotted path (a number or nested lists of numbers)."""
    return max(abs(a - b) for a, b in zip(_numbers(_at(committed, path)), _numbers(_at(rerun, path)), strict=True))

"""Parity check of notebook 01's slice (01_cras_slice.json) against a re-run (#50): pure functions over JSON-like trees.

Open3D's multi-threaded ICP drifts from run to run (about 1e-4 m on the translation, 5e-4 / 7e-4 degrees on yaw / tilt, the 5th
significant digit of the distance statistics, up to +-600 of 3.67 M scan points in the room box; a single-threaded re-run
against the committed slice, 2026-11-23: 1.9e-4 m, 6.8e-4 / 5.8e-5 degrees, 45 points, and one scanner position's last
rounded digit flipped by 1 mm). The tolerances below are 3x (room box points) to 10x or more that drift, and 1 mm is well under
USIBD LOA30's 15 mm, so drift within them is thread noise, not a changed result. Every field without a tolerance must match
exactly."""

from collections.abc import Mapping
from typing import Any, TypeGuard

_DISTANCE_KEYS = ("as delivered", "translation only", "translation + ICP")

# dotted path -> absolute tolerance, in the unit of the field
SLICE_TOLERANCES: dict[str, float] = {
    "frame.scan_to_model_4x4": 1e-3,  # elementwise: 1 mm on the translation column (m), ~0.06 degrees on the rotation entries
    "frame.translation_m": 1e-3,  # m
    "frame.yaw_deg": 0.01,  # degrees
    "frame.tilt_deg": 0.01,  # degrees
    **{f"frame.median_distance_m.{k}": 1e-4 for k in _DISTANCE_KEYS},  # m; 5th significant digit drifts
    **{f"frame.p90_distance_m.{k}": 1e-4 for k in _DISTANCE_KEYS},  # m
    "room.scan_points_in_box": 2000,  # points; the box edge cuts a registered cloud that moves by fractions of a mm
    "uvigo.median_distance_after_ground_truth_m": 1e-4,  # m
    # m; written rounded to 1 mm, so 0.2 mm of transform drift can flip the last digit (15.906 -> 15.905 seen in a re-run)
    "scanner_positions.positions_model_frame": 2e-3,
    "scanner_positions.positions_scan_frame": 2e-3,
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

"""Scoring of the Phase 0.5 gate (docs/roadmap.md): pure functions over the rows that notebooks 05a, 03b and 05b read and write."""

import csv
from pathlib import Path

VERDICTS = ("OK", "shifted", "not confirmed")
HAND_COLUMNS = ["n", "global_id", "ifc_class", "name", "verdict", "judgement", "note"]
PASS, FAIL, PENDING = "PASS", "FAIL", "PENDING"


def read_hand_check(path: Path) -> list[dict]:
    """Rows of the hand-check CSV; blanks stripped; raises ValueError on wrong columns or a judgement outside VERDICTS (or empty)."""
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != HAND_COLUMNS:
            raise ValueError(f"{path}: columns must be {HAND_COLUMNS}, found {reader.fieldnames}")
        rows = [{k: (v or "").strip() for k, v in r.items()} for r in reader]
    for r in rows:
        if r["judgement"] not in ("", *VERDICTS):
            raise ValueError(f"{path}: row n={r['n']}: judgement {r['judgement']!r} is not one of {', '.join(VERDICTS)} (or empty)")
    return rows


def write_hand_check_template(path: Path, rows: list[dict]) -> bool:
    """Write the CSV only if it does not exist yet (the author's entries are never overwritten). Returns whether it wrote."""
    if Path(path).exists():
        return False
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, HAND_COLUMNS)
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in HAND_COLUMNS} for r in rows)
    return True


def hand_check_result(rows: list[dict], n_required: int = 20, min_share: float = 0.8) -> dict:
    """Agreement = judgement equals the verdict, over the filled rows. PENDING until `n_required` rows are filled."""
    filled = [r for r in rows if r["judgement"]]
    n_agree = sum(r["judgement"] == r["verdict"] for r in filled)
    share = n_agree / len(filled) if filled else None
    if len(filled) < n_required:
        status = PENDING
    else:
        status = PASS if share >= min_share else FAIL
    return dict(status=status, n_filled=len(filled), n_agree=n_agree, share=share, n_required=n_required, min_share=min_share)


def perturbed_result(rows: list[dict], tol_mm: float, max_false_share: float = 0.10) -> dict:
    """The roadmap's perturbed-model criterion from 03b's score rows (columns change, injected_offset_mm, expected, actual).

    Beyond tolerance: a move larger than tol_mm, or an element not built. Control: a move within tol_mm (reported, not part of the criterion).
    False flag: an untouched element (empty `change`) whose verdict is shifted or missing."""
    def moved_mm(r):
        return abs(float(r["injected_offset_mm"])) if r["change"] == "moved" else None
    changed = [r for r in rows if r["change"]]
    beyond = [r for r in changed if r["change"] == "not_built" or moved_mm(r) > tol_mm]
    control = [r for r in changed if r["change"] == "moved" and moved_mm(r) <= tol_mm]
    untouched = [r for r in rows if not r["change"]]
    false = [r for r in untouched if r["actual"] in ("shifted", "missing")]
    n_right = sum(r["actual"] == r["expected"] for r in beyond)
    changes_ok = n_right == len(beyond)
    share = len(false) / len(untouched) if untouched else 0.0
    false_ok = share <= max_false_share
    return dict(status=PASS if changes_ok and false_ok else FAIL, n_beyond=len(beyond), n_beyond_right=n_right, changes_ok=changes_ok,
                n_control=len(control), n_control_right=sum(r["actual"] == r["expected"] for r in control),
                n_untouched=len(untouched), n_false=len(false), share_false=share, false_ok=false_ok, max_false_share=max_false_share)


def registration_result(rows: list[dict], min_success: int) -> dict:
    """05a's registration.csv: `success` is 'True' or 'False'."""
    n_success = sum(r["success"] == "True" for r in rows)
    return dict(status=PASS if n_success >= min_success else FAIL, n_success=n_success, n_total=len(rows), min_success=min_success)


def combine(statuses: list[str]) -> str:
    """Overall gate: PASS only if every part passes; any FAIL is final; otherwise PENDING."""
    if FAIL in statuses:
        return FAIL
    return PASS if all(s == PASS for s in statuses) else PENDING

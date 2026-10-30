"""Scoring of the Phase 0.5 gate (docs/roadmap.md): pure functions over the rows that notebooks 05a, 03b and 05b read and write."""

import csv
from pathlib import Path

# The verdicts the hand check can name. "missing" and "not visible" are unreachable in this phase: notebook 01 recovered no scanner
# positions, so 03a cannot tell an unseen element from an absent one, and CONTEXT.md merges both into "not confirmed".
VERDICTS = ("OK", "shifted", "not confirmed")
HAND_COLUMNS = ["n", "global_id", "ifc_class", "name", "verdict", "judgement", "note"]
PASS, FAIL, PENDING = "PASS", "FAIL", "PENDING"


def read_hand_check(path: Path) -> list[dict]:
    """Rows of the hand-check CSV; blanks stripped; raises ValueError on wrong columns or a judgement outside VERDICTS (or empty)."""
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != HAND_COLUMNS:
            raise ValueError(f"{path}: columns must be {HAND_COLUMNS}, found {reader.fieldnames}")
        rows = []
        for r in reader:
            if None in r:
                raise ValueError(f"{path}: row n={r.get('n')}: extra fields {r[None]} (a comma in a note must be quoted)")
            rows.append({k: (v or "").strip() for k, v in r.items()})
    for r in rows:
        if r["judgement"] not in ("", *VERDICTS):
            raise ValueError(f"{path}: row n={r['n']}: judgement {r['judgement']!r} is not one of {', '.join(VERDICTS)} (or empty)")
    return rows


def write_hand_check_template(path: Path, rows: list[dict]) -> bool:
    """Write the CSV only if it does not exist yet (the author's entries are never overwritten). Returns whether it wrote."""
    try:
        f = open(path, "x", newline="")   # exclusive create: no exists/open race
    except FileExistsError:
        return False
    with f:
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


def perturbed_result(rows: list[dict], max_false_share: float = 0.10) -> dict:
    """The roadmap's perturbed-model criterion from 03b's score rows (columns run, change, expected, actual; one run per perturbation).

    Each run must hold exactly one changed row (empty `change` = untouched); ValueError otherwise, and on an unknown `change`.
    Beyond tolerance: a changed row whose `expected` is not 'OK'. 03b derives `expected` (LOA30 on the true deviation of the wall's plane,
    so the 3 and 10 cm moves and the deletions are beyond tolerance), and this function does not recompute it. Control: a changed row
    expected OK (the 1 cm moves), reported but not part of the criterion. ValueError when no change is beyond tolerance (vacuous pass).
    `changes_ok`: every beyond-tolerance changed row has actual == expected.

    False flag: an untouched row whose actual is shifted or missing ("missing" is unreachable in this phase, see VERDICTS, so in practice
    shifted only). The clause is applied **per run**: every run's share of falsely flagged untouched elements must be <= max_false_share,
    so `false_ok` uses the worst run (`worst_run`, `worst_share_false`; the first run in the rows on a tie). `per_run` has each run's
    n_untouched, n_false, share_false and n_untouched_not_confirmed; `pooled_share_false` (all runs together) is context only.
    `n_untouched_not_confirmed` is pooled over the runs (context; "not confirmed" is not a false flag)."""
    for r in rows:
        if r["change"] not in ("", "moved", "not_built"):
            raise ValueError(f"unknown change {r['change']!r}; expected '', 'moved' or 'not_built'")
    runs = list(dict.fromkeys(r["run"] for r in rows))
    for run in runs:
        n = sum(bool(r["change"]) for r in rows if r["run"] == run)
        if n != 1:
            raise ValueError(f"run {run!r} has {n} changed rows; each run must have exactly one")
    changed = [r for r in rows if r["change"]]
    beyond = [r for r in changed if r["expected"] != "OK"]
    if not beyond:
        raise ValueError("no change beyond tolerance in the rows: the criterion would pass vacuously")
    control = [r for r in changed if r["expected"] == "OK"]
    n_right = sum(r["actual"] == r["expected"] for r in beyond)
    changes_ok = n_right == len(beyond)

    per_run = {}
    for run in runs:
        untouched = [r for r in rows if r["run"] == run and not r["change"]]
        n_false = sum(r["actual"] in ("shifted", "missing") for r in untouched)
        per_run[run] = dict(n_untouched=len(untouched), n_false=n_false, share_false=n_false / len(untouched) if untouched else 0.0,
                            n_untouched_not_confirmed=sum(r["actual"] == "not confirmed" for r in untouched))
    worst_run = max(per_run, key=lambda run: per_run[run]["share_false"])
    worst_share = per_run[worst_run]["share_false"]
    false_rows = [r for r in rows if not r["change"] and r["actual"] in ("shifted", "missing")]
    n_untouched = sum(p["n_untouched"] for p in per_run.values())
    false_ok = worst_share <= max_false_share
    return dict(status=PASS if changes_ok and false_ok else FAIL, beyond_rows=beyond, false_rows=false_rows, n_beyond=len(beyond), n_beyond_right=n_right,
                changes_ok=changes_ok, n_control=len(control), n_control_right=sum(r["actual"] == r["expected"] for r in control),
                per_run=per_run, worst_run=worst_run, worst_share_false=worst_share, false_ok=false_ok, max_false_share=max_false_share,
                n_untouched=n_untouched, n_false=len(false_rows), pooled_share_false=len(false_rows) / n_untouched if n_untouched else 0.0,
                n_untouched_not_confirmed=sum(p["n_untouched_not_confirmed"] for p in per_run.values()))


def registration_result(rows: list[dict], min_success: int) -> dict:
    """05a's registration.csv: `success` is 'True' or 'False'."""
    for r in rows:
        if r["success"] not in ("True", "False"):
            raise ValueError(f"success must be 'True' or 'False', found {r['success']!r}")
    n_success = sum(r["success"] == "True" for r in rows)
    return dict(status=PASS if n_success >= min_success else FAIL, n_success=n_success, n_total=len(rows), min_success=min_success)


def combine(statuses: list[str]) -> str:
    """Overall gate: PASS only if every part passes; any FAIL is final; otherwise PENDING."""
    if FAIL in statuses:
        return FAIL
    return PASS if all(s == PASS for s in statuses) else PENDING

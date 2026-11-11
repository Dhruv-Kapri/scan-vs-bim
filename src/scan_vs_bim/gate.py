"""Scoring of the Phase 0.5 gate (docs/roadmap.md): pure functions over the rows that notebooks 05a, 03b and 05b read and write."""

import csv
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import TypedDict

# The verdicts the hand check can name. "missing" and "not visible" are unreachable in this phase: notebook 01 recovered no scanner
# positions, so 03a cannot tell an unseen element from an absent one, and CONTEXT.md merges both into "not confirmed".
VERDICTS = ("OK", "shifted", "not confirmed")
HAND_COLUMNS = ["n", "global_id", "ifc_class", "name", "verdict", "judgement", "note"]
PASS, FAIL, PENDING = "PASS", "FAIL", "PENDING"


class ScoreRow(TypedDict):
    """The columns of 03b's scores_*.csv that this module reads (the rows carry more at runtime; they are returned as the same objects)."""
    run: str
    change: str     # "", "moved" or "deleted"; empty = untouched
    expected: str   # a verdict (VERDICTS); only read on changed rows
    actual: str     # the verdict 03a gave on the perturbed model
    baseline: str   # the verdict on the real unperturbed model; only read on untouched rows


class HandRow(TypedDict):
    """One row of the hand-check CSV (HAND_COLUMNS)."""
    n: str
    global_id: str
    ifc_class: str
    name: str
    verdict: str     # 03a's verdict
    judgement: str   # the author's call (VERDICTS), empty until filled
    note: str


class HandCheckResult(TypedDict):
    status: str
    n_filled: int
    n_agree: int
    share: float | None   # n_agree / n_filled; None when nothing is filled
    n_required: int
    min_share: float


class RunFalseFlags(TypedDict):
    """One perturbed run's false-flag counts."""
    n_untouched: int   # every untouched row, baseline-shifted included: NOT the denominator of share_false; use n_counted
    n_baseline_shifted: int
    n_counted: int   # n_untouched minus n_baseline_shifted: the denominator of share_false
    n_false: int
    share_false: float   # n_false / n_counted
    n_untouched_not_confirmed: int


class PerturbedResult(TypedDict):
    status: str
    beyond_rows: list[ScoreRow]   # the input rows themselves
    false_rows: list[ScoreRow]
    excluded_rows: list[ScoreRow]
    n_beyond: int
    n_beyond_right: int
    changes_ok: bool
    n_control: int
    n_control_right: int
    per_run: dict[str, RunFalseFlags]
    worst_run: str
    worst_share_false: float
    false_ok: bool
    max_false_share: float
    n_untouched: int   # every untouched row, baseline-shifted included: NOT the denominator of pooled_share_false; use n_counted
    n_excluded: int
    n_counted: int   # n_untouched minus n_excluded
    n_false: int
    pooled_share_false: float   # n_false / n_counted, over all runs (context only)
    n_untouched_not_confirmed: int


class RegistrationResult(TypedDict):
    status: str
    n_success: int
    n_total: int
    min_success: int


def read_hand_check(path: Path) -> list[HandRow]:
    """Rows of the hand-check CSV; blanks stripped; raises ValueError on wrong columns or a judgement outside VERDICTS (or empty)."""
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != HAND_COLUMNS:
            raise ValueError(f"{path}: columns must be {HAND_COLUMNS}, found {reader.fieldnames}")
        rows: list[HandRow] = []
        for r in reader:
            if None in r:
                raise ValueError(f"{path}: row n={r.get('n')}: extra fields {r[None]} (a comma in a note must be quoted)")
            c = {k: (v or "").strip() for k, v in r.items()}
            rows.append(HandRow(n=c["n"], global_id=c["global_id"], ifc_class=c["ifc_class"], name=c["name"], verdict=c["verdict"],
                                judgement=c["judgement"], note=c["note"]))
    for row in rows:
        if row["judgement"] not in ("", *VERDICTS):
            raise ValueError(f"{path}: row n={row['n']}: judgement {row['judgement']!r} is not one of {', '.join(VERDICTS)} (or empty)")
    return rows


def write_hand_check_template(path: Path, rows: Iterable[Mapping[str, object]]) -> bool:
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


def hand_check_result(rows: Sequence[HandRow], *, n_required: int, min_share: float) -> HandCheckResult:
    """Agreement = judgement equals the verdict, over the filled rows. PENDING until `n_required` rows are filled."""
    filled = [r for r in rows if r["judgement"]]
    n_agree = sum(r["judgement"] == r["verdict"] for r in filled)
    share = n_agree / len(filled) if filled else None
    if share is None or len(filled) < n_required:
        status = PENDING
    else:
        status = PASS if share >= min_share else FAIL
    return HandCheckResult(status=status, n_filled=len(filled), n_agree=n_agree, share=share, n_required=n_required, min_share=min_share)


def perturbed_result(rows: Sequence[ScoreRow], *, max_false_share: float) -> PerturbedResult:
    """The roadmap's perturbed-model criterion from 03b's score rows (columns run, change, expected, actual, baseline; one run per perturbation).

    Each run must hold exactly one changed row (empty `change` = untouched); ValueError otherwise, on an unknown `change`, and on a changed
    row whose `expected` is not one of VERDICTS.
    Beyond tolerance: a changed row whose `expected` is not 'OK'. 03b derives `expected` (LOA30 on the true deviation of the wall's plane,
    so the 3 and 10 cm moves and the deletions are beyond tolerance), and this function does not recompute it. Control: a changed row
    expected OK (the 1 cm moves), reported but not part of the criterion. ValueError when no change is beyond tolerance (vacuous pass).
    `changes_ok`: every beyond-tolerance changed row has actual == expected.

    False flag (docs/adr/0002-false-flags-against-baseline.md, CONTEXT.md "False flag"): an untouched row whose verdict CHANGES from its `baseline`
    (the verdict on the real unperturbed model) to shifted or missing ("missing" is unreachable in this phase, see VERDICTS, so in practice
    shifted only). An untouched row whose baseline is already shifted may really be displaced: it leaves the denominator and is returned in
    `excluded_rows`. ValueError on an untouched row whose `baseline` is missing or not one of VERDICTS (scores from a 03b without the column).
    The clause is applied **per run**: every run's share of falsely flagged elements among the counted ones (untouched minus baseline-shifted)
    must be <= max_false_share, so `false_ok` uses the worst run (`worst_run`, `worst_share_false`; the first run in the rows on a tie).
    `per_run` has each run's n_untouched, n_baseline_shifted, n_counted, n_false, share_false (n_false / n_counted) and n_untouched_not_confirmed;
    `pooled_share_false` (all runs together) is context only. `n_untouched_not_confirmed` is pooled over the runs (context; "not confirmed" is not a false flag)."""
    for r in rows:
        if r["change"] not in ("", "moved", "deleted"):
            raise ValueError(f"unknown change {r['change']!r}; expected '', 'moved' or 'deleted'")
    runs = list(dict.fromkeys(r["run"] for r in rows))
    for run in runs:
        n = sum(bool(r["change"]) for r in rows if r["run"] == run)
        if n != 1:
            raise ValueError(f"run {run!r} has {n} changed rows; each run must have exactly one")
    untouched_rows: list[tuple[ScoreRow, str]] = []   # each untouched row with its validated baseline
    for r in rows:
        if not r["change"]:
            baseline = r.get("baseline")
            if baseline not in VERDICTS:
                raise ValueError(f"run {r['run']!r}: untouched row has baseline {baseline!r}, not one of {', '.join(VERDICTS)} (scores from a 03b without the baseline column?)")
            untouched_rows.append((r, baseline))
    changed = [r for r in rows if r["change"]]
    for r in changed:
        if r["expected"] not in VERDICTS:
            raise ValueError(f"run {r['run']!r}: expected {r['expected']!r} is not one of {', '.join(VERDICTS)}")
    beyond = [r for r in changed if r["expected"] != "OK"]
    if not beyond:
        raise ValueError("no change beyond tolerance in the rows: the criterion would pass vacuously")
    control = [r for r in changed if r["expected"] == "OK"]
    n_right = sum(r["actual"] == r["expected"] for r in beyond)
    changes_ok = n_right == len(beyond)

    excluded_rows = [r for r, b in untouched_rows if b == "shifted"]   # may really be displaced (ADR 0002): out of the denominator
    false_rows = [r for r, b in untouched_rows if b != "shifted" and r["actual"] in ("shifted", "missing")]
    per_run: dict[str, RunFalseFlags] = {}
    for run in runs:
        untouched = [r for r, _ in untouched_rows if r["run"] == run]
        n_baseline_shifted = sum(r["run"] == run for r in excluded_rows)
        n_counted = len(untouched) - n_baseline_shifted
        n_false = sum(r["run"] == run for r in false_rows)
        per_run[run] = RunFalseFlags(n_untouched=len(untouched), n_baseline_shifted=n_baseline_shifted, n_counted=n_counted, n_false=n_false,
                                    share_false=n_false / n_counted if n_counted else 0.0,
                                    n_untouched_not_confirmed=sum(r["actual"] == "not confirmed" for r in untouched))
    worst_run = max(per_run, key=lambda run: per_run[run]["share_false"])
    worst_share = per_run[worst_run]["share_false"]
    n_untouched = sum(p["n_untouched"] for p in per_run.values())
    n_counted = sum(p["n_counted"] for p in per_run.values())
    false_ok = worst_share <= max_false_share
    return PerturbedResult(status=PASS if changes_ok and false_ok else FAIL, beyond_rows=beyond, false_rows=false_rows, excluded_rows=excluded_rows,
                           n_beyond=len(beyond), n_beyond_right=n_right,
                           changes_ok=changes_ok, n_control=len(control), n_control_right=sum(r["actual"] == r["expected"] for r in control),
                           per_run=per_run, worst_run=worst_run, worst_share_false=worst_share, false_ok=false_ok, max_false_share=max_false_share,
                           n_untouched=n_untouched, n_excluded=len(excluded_rows), n_counted=n_counted, n_false=len(false_rows),
                           pooled_share_false=len(false_rows) / n_counted if n_counted else 0.0,
                           n_untouched_not_confirmed=sum(p["n_untouched_not_confirmed"] for p in per_run.values()))


def registration_result(rows: Sequence[Mapping[str, str]], min_success: int) -> RegistrationResult:
    """05a's registration.csv: `success` is 'True' or 'False'."""
    for r in rows:
        if r["success"] not in ("True", "False"):
            raise ValueError(f"success must be 'True' or 'False', found {r['success']!r}")
    n_success = sum(r["success"] == "True" for r in rows)
    return RegistrationResult(status=PASS if n_success >= min_success else FAIL, n_success=n_success, n_total=len(rows), min_success=min_success)


def combine(statuses: Sequence[str]) -> str:
    """Overall gate: PASS only if every part passes; any FAIL is final; otherwise PENDING."""
    if FAIL in statuses:
        return FAIL
    return PASS if all(s == PASS for s in statuses) else PENDING

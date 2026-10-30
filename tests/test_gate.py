import csv

import pytest

from scan_vs_bim.gate import combine, hand_check_result, perturbed_result, read_hand_check, registration_result, write_hand_check_template

COLUMNS = ["n", "global_id", "ifc_class", "name", "verdict", "judgement", "note"]


def hand_rows(verdicts, judgements):
    return [dict(n=i + 1, global_id=f"g{i}", ifc_class="IfcWall", name=f"w{i}", verdict=v, judgement=j, note="")
            for i, (v, j) in enumerate(zip(verdicts, judgements))]


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, COLUMNS)
        w.writeheader()
        w.writerows(rows)


def test_hand_check_pending_until_all_are_filled():
    rows = hand_rows(["OK"] * 20, ["OK"] * 19 + [""])
    r = hand_check_result(rows)
    assert r["status"] == "PENDING" and r["n_filled"] == 19 and r["n_agree"] == 19


def test_hand_check_agreement_is_judgement_equals_verdict():
    verdicts = ["OK"] * 10 + ["shifted"] * 5 + ["not confirmed"] * 5
    judgements = ["OK"] * 10 + ["shifted"] * 3 + ["OK"] * 2 + ["not confirmed"] * 4 + ["shifted"]
    r = hand_check_result(hand_rows(verdicts, judgements))
    assert (r["n_filled"], r["n_agree"]) == (20, 17) and r["share"] == pytest.approx(0.85) and r["status"] == "PASS"


def test_hand_check_threshold_is_at_least_80_percent():
    verdicts = ["OK"] * 20
    assert hand_check_result(hand_rows(verdicts, ["OK"] * 16 + ["shifted"] * 4))["status"] == "PASS"   # 16 / 20 = 80 %
    assert hand_check_result(hand_rows(verdicts, ["OK"] * 15 + ["shifted"] * 5))["status"] == "FAIL"   # 75 %


def test_hand_check_with_nothing_filled_is_pending():
    r = hand_check_result(hand_rows(["OK"] * 20, [""] * 20))
    assert r["status"] == "PENDING" and r["n_filled"] == 0 and r["share"] is None


def test_read_hand_check_rejects_unknown_judgement(tmp_path):
    p = tmp_path / "h.csv"
    write_csv(p, hand_rows(["OK", "OK"], ["OK", "okay"]))
    with pytest.raises(ValueError, match=r"row n=2.*'okay'.*OK.*shifted.*not confirmed"):
        read_hand_check(p)


def test_read_hand_check_strips_blanks_and_rejects_bad_columns(tmp_path):
    p = tmp_path / "h.csv"
    write_csv(p, hand_rows(["OK"], [" shifted "]))
    assert read_hand_check(p)[0]["judgement"] == "shifted"
    p.write_text("n,global_id\n1,a\n")
    with pytest.raises(ValueError, match="columns"):
        read_hand_check(p)


def test_read_hand_check_rejects_rows_with_extra_fields(tmp_path):
    p = tmp_path / "h.csv"
    write_csv(p, hand_rows(["OK"], [""]))
    p.write_text(p.read_text().rstrip("\n") + ",oops\n")
    with pytest.raises(ValueError, match="extra"):
        read_hand_check(p)


def test_write_hand_check_template_never_overwrites(tmp_path):
    p = tmp_path / "h.csv"
    rows = hand_rows(["OK", "shifted"], ["", ""])
    assert write_hand_check_template(p, rows) is True
    assert [r["judgement"] for r in read_hand_check(p)] == ["", ""]
    write_csv(p, hand_rows(["OK", "shifted"], ["OK", "shifted"]))  # the author's entries
    assert write_hand_check_template(p, rows) is False
    assert [r["judgement"] for r in read_hand_check(p)] == ["OK", "shifted"]


def score_row(run="r1", change="", expected="", actual="OK"):
    return dict(run=run, change=change, expected=expected, actual=actual)


def run_rows(run, changed, n_untouched=34, **untouched_actuals):
    """One 03b run: the changed row plus `n_untouched` untouched rows (all OK unless `shifted=k` etc. replaces the first k)."""
    untouched = [score_row(run, actual=a) for a, k in untouched_actuals.items() for _ in range(k)]
    return [changed] + untouched + [score_row(run) for _ in range(n_untouched - len(untouched))]


def test_perturbed_run_must_have_exactly_one_changed_row():
    good = run_rows("r1", score_row("r1", "moved", "shifted", "shifted"))
    with pytest.raises(ValueError, match="r2.*exactly one"):   # no changed row in r2
        perturbed_result(good + [score_row("r2") for _ in range(5)])
    two = run_rows("r2", score_row("r2", "moved", "shifted", "shifted")) + [score_row("r2", "not_built", "not confirmed", "not confirmed")]
    with pytest.raises(ValueError, match="r2.*exactly one"):   # two changed rows in r2
        perturbed_result(good + two)


def seven_runs(**actual_by_run):
    """Seven runs shaped like 03b's: two 1 cm moves (control), 3 and 10 cm moves, three deletions; `actual_by_run` overrides the changed row's actual."""
    spec = [("move_1cm_away", "moved", "OK"), ("move_1cm_in", "moved", "OK"), ("move_3cm_in", "moved", "shifted"), ("move_10cm_in", "moved", "shifted"),
            ("delete_door", "not_built", "not confirmed"), ("delete_slab", "not_built", "not confirmed"), ("delete_wall", "not_built", "not confirmed")]
    return [row for run, change, expected in spec
            for row in run_rows(run, score_row(run, change, expected, actual_by_run.get(run, expected)))]


def test_perturbed_beyond_tolerance_is_decided_by_the_expected_verdict_not_the_size_of_the_move():
    rows = seven_runs(move_3cm_in="not confirmed")   # one beyond-tolerance change gets the wrong verdict
    r = perturbed_result(rows)
    assert (r["n_beyond"], r["n_beyond_right"]) == (5, 4) and r["changes_ok"] is False and r["status"] == "FAIL"
    assert [x["run"] for x in r["beyond_rows"]] == ["move_3cm_in", "move_10cm_in", "delete_door", "delete_slab", "delete_wall"]
    assert perturbed_result(seven_runs())["changes_ok"] is True


def test_perturbed_one_cm_move_expected_ok_is_a_control_not_part_of_the_criterion():
    rows = seven_runs(move_1cm_away="not confirmed", move_1cm_in="shifted")   # both controls read wrong
    r = perturbed_result(rows)
    assert (r["n_control"], r["n_control_right"]) == (2, 0)
    assert (r["n_beyond"], r["n_beyond_right"]) == (5, 5) and r["changes_ok"] is True and r["status"] == "PASS"
    assert perturbed_result(seven_runs())["n_control_right"] == 2


def test_perturbed_false_flag_clause_is_judged_per_run_on_the_worst_run():
    flagged = lambda run, k: run_rows(run, score_row(run, "moved", "shifted", "shifted"), shifted=k)
    rows = flagged("a", 0) + flagged("b", 3) + flagged("c", 1)   # 34 untouched each: 3 of 34 = 8.8 %
    r = perturbed_result(rows)
    assert r["worst_run"] == "b" and r["worst_share_false"] == pytest.approx(3 / 34) and r["false_ok"] is True and r["status"] == "PASS"
    assert [r["per_run"][k]["n_false"] for k in "abc"] == [0, 3, 1]
    assert r["pooled_share_false"] == pytest.approx(4 / 102) and r["n_false"] == 4 and r["n_untouched"] == 102
    # 4 of 34 = 11.8 % in one run fails, although pooled over the three runs it is only 4 of 102 = 3.9 %
    rows = flagged("a", 0) + flagged("b", 4) + flagged("c", 0)
    r = perturbed_result(rows)
    assert r["worst_run"] == "b" and r["false_ok"] is False and r["changes_ok"] is True and r["status"] == "FAIL"
    assert r["pooled_share_false"] < 0.10 < r["worst_share_false"]


def test_perturbed_false_flag_threshold_is_at_most_10_percent_and_counts_missing_too():
    ten = run_rows("a", score_row("a", "not_built", "not confirmed", "not confirmed"), n_untouched=30, shifted=2, missing=1)   # 3 of 30 = 10 %
    r = perturbed_result(ten)
    assert r["status"] == "PASS" and r["worst_share_false"] == pytest.approx(0.10)
    over = run_rows("a", score_row("a", "not_built", "not confirmed", "not confirmed"), n_untouched=30, shifted=3, missing=1)
    assert perturbed_result(over)["status"] == "FAIL"


def test_perturbed_not_confirmed_is_not_a_false_flag():
    rows = run_rows("a", score_row("a", "not_built", "not confirmed", "not confirmed"), n_untouched=10, **{"not confirmed": 10}) + \
           run_rows("b", score_row("b", "not_built", "not confirmed", "not confirmed"), n_untouched=10, **{"not confirmed": 4})
    r = perturbed_result(rows)
    assert r["n_false"] == 0 and r["n_untouched_not_confirmed"] == 14 and r["per_run"]["b"]["n_untouched_not_confirmed"] == 4


def test_perturbed_returns_the_flagged_untouched_rows():
    flagged = score_row("a", actual="shifted")
    rows = [score_row("a", "not_built", "not confirmed", "not confirmed"), flagged, score_row("a")]
    r = perturbed_result(rows)
    assert r["false_rows"] == [flagged] and r["beyond_rows"] == [rows[0]]


def test_perturbed_without_changes_beyond_tolerance_raises_not_passes_vacuously():
    rows = run_rows("a", score_row("a", "moved", "OK", "OK"), n_untouched=5)   # only a within-tolerance control
    with pytest.raises(ValueError, match="beyond"):
        perturbed_result(rows)
    rows += run_rows("b", score_row("b", "moved", "OK", "OK"), n_untouched=5)
    with pytest.raises(ValueError, match="beyond"):
        perturbed_result(rows)


def test_perturbed_unknown_change_raises_naming_it():
    with pytest.raises(ValueError, match="'rotated'"):
        perturbed_result([score_row("a", "rotated", "shifted", "shifted")])


def test_registration_criterion_counts_success_flags():
    rows = [{"success": s} for s in ["True"] * 4 + ["False"] * 5]
    r = registration_result(rows, min_success=6)
    assert (r["n_success"], r["n_total"], r["status"]) == (4, 9, "FAIL")
    assert registration_result([{"success": "True"}] * 6 + [{"success": "False"}] * 3, 6)["status"] == "PASS"


def test_registration_rejects_other_success_values():
    for bad in ("", "true", "1", "yes"):
        with pytest.raises(ValueError, match="success"):
            registration_result([{"success": "True"}, {"success": bad}], min_success=1)


def test_combine_overall():
    assert combine(["PASS", "PASS", "PASS"]) == "PASS"
    assert combine(["PASS", "FAIL", "PENDING"]) == "FAIL"   # a failure is final, even with a part pending
    assert combine(["PASS", "PASS", "PENDING"]) == "PENDING"

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


def test_write_hand_check_template_never_overwrites(tmp_path):
    p = tmp_path / "h.csv"
    rows = hand_rows(["OK", "shifted"], ["", ""])
    assert write_hand_check_template(p, rows) is True
    assert [r["judgement"] for r in read_hand_check(p)] == ["", ""]
    write_csv(p, hand_rows(["OK", "shifted"], ["OK", "shifted"]))  # the author's entries
    assert write_hand_check_template(p, rows) is False
    assert [r["judgement"] for r in read_hand_check(p)] == ["OK", "shifted"]


def score_row(change="", injected="", expected="", actual="OK"):
    return dict(change=change, injected_offset_mm=injected, expected=expected, actual=actual)


def test_perturbed_criterion_counts_changes_beyond_tolerance_only():
    rows = [score_row("moved", "10.0", "OK", "not confirmed"),         # 1 cm control: within 15 mm, reported, not in the criterion
            score_row("moved", "30.0", "shifted", "shifted"),
            score_row("moved", "100.0", "shifted", "not confirmed"),
            score_row("not_built", "", "not confirmed", "not confirmed")] + [score_row() for _ in range(29)]
    r = perturbed_result(rows, tol_mm=15.0)
    assert (r["n_beyond"], r["n_beyond_right"]) == (3, 2) and r["changes_ok"] is False
    assert (r["n_control"], r["n_control_right"]) == (1, 0)
    assert r["n_untouched"] == 29 and r["n_false"] == 0 and r["false_ok"] is True and r["status"] == "FAIL"


def test_perturbed_criterion_passes_when_all_right_and_false_rate_at_most_10_percent():
    rows = [score_row("moved", "30.0", "shifted", "shifted"), score_row("not_built", "", "not confirmed", "not confirmed")]
    rows += [score_row(actual="shifted")] * 3 + [score_row(actual="OK")] * 27   # 3 of 30 = 10 %
    r = perturbed_result(rows, tol_mm=15.0)
    assert r["status"] == "PASS" and r["share_false"] == pytest.approx(0.10)
    rows[-1] = score_row(actual="missing")
    rows += [score_row(actual="shifted")]  # now 5 of 31 untouched
    assert perturbed_result(rows, tol_mm=15.0)["status"] == "FAIL"


def test_perturbed_criterion_not_confirmed_is_not_a_false_flag():
    rows = [score_row(actual="not confirmed")] * 10
    assert perturbed_result(rows, tol_mm=15.0)["n_false"] == 0


def test_registration_criterion_counts_success_flags():
    rows = [{"success": s} for s in ["True"] * 4 + ["False"] * 5]
    r = registration_result(rows, min_success=6)
    assert (r["n_success"], r["n_total"], r["status"]) == (4, 9, "FAIL")
    assert registration_result([{"success": "True"}] * 6 + [{"success": "False"}] * 3, 6)["status"] == "PASS"


def test_combine_overall():
    assert combine(["PASS", "PASS", "PASS"]) == "PASS"
    assert combine(["PASS", "FAIL", "PENDING"]) == "FAIL"   # a failure is final, even with a part pending
    assert combine(["PASS", "PASS", "PENDING"]) == "PENDING"

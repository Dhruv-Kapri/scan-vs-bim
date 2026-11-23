import copy
import json
from pathlib import Path
from typing import Any

from scan_vs_bim.slice_parity import SLICE_TOLERANCES, max_abs_drift, slice_mismatches

SLICE_PATH = Path(__file__).parents[1] / "notebooks" / "01_cras_slice.json"


def _committed() -> dict[str, Any]:
    return json.loads(SLICE_PATH.read_text())


def test_identical_slices_match() -> None:
    s = _committed()
    assert slice_mismatches(s, copy.deepcopy(s)) == []


def test_drift_within_tolerance_passes_and_beyond_it_names_the_path() -> None:
    s = _committed()
    ok = copy.deepcopy(s)
    ok["frame"]["translation_m"][0] += 5e-4
    ok["frame"]["scan_to_model_4x4"][0][3] += 5e-4
    ok["room"]["scan_points_in_box"] += 600
    assert slice_mismatches(s, ok) == []

    bad = copy.deepcopy(s)
    bad["frame"]["translation_m"][0] += 2e-3
    bad["frame"]["scan_to_model_4x4"][1][1] += 2e-3
    msgs = slice_mismatches(s, bad)
    assert len(msgs) == 2
    assert any(m.startswith("frame.translation_m[0]") and "0.001" in m for m in msgs)
    assert any(m.startswith("frame.scan_to_model_4x4[1][1]") for m in msgs)


def test_fields_without_a_tolerance_must_match_exactly() -> None:
    s = _committed()
    bad = copy.deepcopy(s)
    bad["room"]["element_global_ids"][3] = "x" + bad["room"]["element_global_ids"][3][1:]
    bad["room"]["box_model_frame"]["xmin"] += 1e-9
    msgs = slice_mismatches(s, bad)
    assert len(msgs) == 2
    assert all("exact" in m for m in msgs)


def test_missing_key_is_reported() -> None:
    s = _committed()
    bad = copy.deepcopy(s)
    del bad["uvigo"]["scale"]
    assert any(m.startswith("uvigo.scale") for m in slice_mismatches(s, bad))


def test_max_abs_drift_reads_scalars_and_nested_lists() -> None:
    s = _committed()
    r = copy.deepcopy(s)
    r["frame"]["scan_to_model_4x4"][2][3] += 3e-4
    r["frame"]["yaw_deg"] += 1e-4
    assert abs(max_abs_drift(s, r, "frame.scan_to_model_4x4") - 3e-4) < 1e-9
    assert abs(max_abs_drift(s, r, "frame.yaw_deg") - 1e-4) < 1e-9


def test_every_tolerance_path_exists_in_the_committed_slice() -> None:
    s = _committed()
    for path in SLICE_TOLERANCES:
        assert max_abs_drift(s, s, path) == 0.0, path

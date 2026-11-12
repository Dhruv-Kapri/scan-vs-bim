from pathlib import Path

from scan_vs_bim.tables import read_rows


def test_read_rows_keeps_order_and_text_and_reads_blanks_as_empty(tmp_path: Path) -> None:
    # The notebooks look rows up by position (05b's draw indexes 03a's rows) and parse numbers themselves: order and the raw strings must survive.
    path = tmp_path / "t.csv"
    path.write_text('global_id,median_signed_offset_mm,reason\nb,-1.90,\na,,"no points, none"\n')
    assert read_rows(path) == [{"global_id": "b", "median_signed_offset_mm": "-1.90", "reason": ""},
                               {"global_id": "a", "median_signed_offset_mm": "", "reason": "no points, none"}]

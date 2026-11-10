import csv
import shutil
from pathlib import Path

import pytest

from run_notebook import run_notebook

ROOT = Path(__file__).parents[1]
NOTEBOOK = ROOT / "notebooks" / "04b_carbon.ipynb"
MAPPING = ROOT / "notebooks" / "04b_material_mapping.csv"
IFC = ROOT / "data" / "cras" / "craslabbim.ifc"
OEKO = ROOT / "data" / "oekobaudat"
CSVS = {v: ROOT / "outputs" / "03a" / f"verdicts_{v}.csv" for v in ("no_labels", "oracle_labels")}


def read(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_mapping_has_identifiers_only() -> None:
    """Cheap guard for the licence rule: the committed mapping holds no factor values."""
    columns = list(read(MAPPING)[0])
    assert columns == ["ifc_material", "oekobaudat_uuid", "basis", "dataset_name", "note"]
    for r in read(MAPPING):
        assert r["basis"] in ("", "volume", "opening_area")
        assert bool(r["oekobaudat_uuid"]) == bool(r["basis"]) == bool(r["dataset_name"])  # a mapped material has all three, an unmapped one none


def test_notebook_04b_carbon_table_adds_up(tmp_path: Path) -> None:
    """One row per room element in carbon_elements.csv; carbon_summary.csv splits it into confirmed + rest = total per variant; every mapped dataset is used or reported;
    only outputs/04b/ is new."""
    for p in [IFC, *CSVS.values()]:
        if not p.exists():
            pytest.skip(f"{p.relative_to(ROOT)} missing (download the data; run notebook 03a)")
    if not (OEKO / "processes").exists():
        pytest.skip("data/oekobaudat missing (run scripts/fetch_oekobaudat.py)")
    # Run a copy so the committed notebook is not rewritten and its outputs land in tmp_path, not the real outputs/.
    (tmp_path / "notebooks").mkdir()
    (tmp_path / "outputs" / "03a").mkdir(parents=True)
    (tmp_path / "data").symlink_to(ROOT / "data")
    for p in CSVS.values():
        shutil.copy(p, tmp_path / "outputs" / "03a")
    shutil.copy(MAPPING, tmp_path / "notebooks")
    copy = shutil.copy(NOTEBOOK, tmp_path / "notebooks")
    run_notebook(Path(copy), timeout=1800)

    out = tmp_path / "outputs" / "04b"
    elements, layers = read(out / "carbon_elements.csv"), read(out / "carbon_layers.csv")
    verdicts = {v: {r["global_id"]: r["verdict"] for r in read(p)} for v, p in CSVS.items()}
    assert [r["global_id"] for r in elements] == list(verdicts["no_labels"])  # one row per room element, in 03a's order
    assert len(elements) == 35

    kg = {r["global_id"]: float(r["kg_co2e_a1_a3"]) for r in elements}
    summary = {r["variant"]: r for r in read(out / "carbon_summary.csv")}
    assert set(summary) == set(CSVS)
    for variant, column in (("no_labels", "verdict_no_labels"), ("oracle_labels", "verdict_oracle_labels")):
        assert all(r[column] == verdicts[variant][r["global_id"]] for r in elements)
        confirmed = [g for g in kg if verdicts[variant][g] in ("OK", "shifted")]
        s = summary[variant]
        assert int(s["confirmed_elements"]) == len(confirmed) and int(s["rest_elements"]) == len(kg) - len(confirmed)
        assert float(s["confirmed_kg_co2e_a1_a3"]) == pytest.approx(sum(kg[g] for g in confirmed), abs=0.5)
        assert float(s["confirmed_kg_co2e_a1_a3"]) + float(s["rest_kg_co2e_a1_a3"]) == pytest.approx(float(s["total_kg_co2e_a1_a3"]), abs=1)
        assert float(s["total_kg_co2e_a1_a3"]) == pytest.approx(sum(kg.values()), abs=0.5)

    assert sum(float(r["kg_co2e_a1_a3"] or 0) for r in layers) == pytest.approx(sum(float(r["kg_co2e_a1_a3"]) for r in elements), abs=0.05 * len(elements))
    assert {r["quantification"] for r in layers} <= {"counted", "unmapped", "not quantifiable"}
    mapped = {r["oekobaudat_uuid"] for r in read(MAPPING) if r["oekobaudat_uuid"]}
    assert mapped <= {r["oekobaudat_uuid"] for r in layers}  # each mapped dataset is counted or reported as not quantifiable

    # Stand-ins: each counted one's kg is the sum of its rows in carbon_layers.csv; the zero ones are named.
    uuid_of = {r["ifc_material"]: r["oekobaudat_uuid"] for r in read(MAPPING)}
    stand_ins = {r["stand_in"]: r for r in read(out / "stand_ins.csv")}
    matches = {"screed": lambda r: r["ifc_material"] == "Contrapiso",
               "brick": lambda r: r["ifc_material"] == "Bloco cerâmico (9cm)",
               "windows": lambda r: r["oekobaudat_uuid"] == uuid_of["Alumínio"],
               "door": lambda r: r["oekobaudat_uuid"] == uuid_of["RAL 5005"]}
    for key, match in matches.items():
        (row,) = [r for name, r in stand_ins.items() if key in name.lower()]
        assert row["treatment"] == "counted"
        expected = sum(float(r["kg_co2e_a1_a3"]) for r in layers if match(r) and r["quantification"] == "counted")
        assert expected > 0 and float(row["kg_co2e_a1_a3"]) == pytest.approx(expected, abs=0.01)
        assert float(row["no_labels_confirmed_kg"]) + float(row["no_labels_rest_kg"]) == pytest.approx(expected, abs=0.01)
        assert float(row["oracle_labels_confirmed_kg"]) + float(row["oracle_labels_rest_kg"]) == pytest.approx(expected, abs=0.01)
        assert float(row["share_of_total"]) == pytest.approx(expected / sum(kg.values()), abs=1e-3)
    assert sum(r["treatment"] == "counted" for r in stand_ins.values()) == 4
    assert [n for n, r in stand_ins.items() if r["treatment"] == "zero"] and all(float(r["kg_co2e_a1_a3"]) == 0 for r in stand_ins.values() if r["treatment"] == "zero")
    assert any("paint" in n.lower() or "pintura" in n.lower() for n in stand_ins) and any("column" in n.lower() for n in stand_ins)

    assert {p.name for p in tmp_path.iterdir()} == {"data", "notebooks", "outputs"}
    assert {p.name for p in (tmp_path / "outputs").iterdir()} == {"03a", "04b"}  # only outputs/04b/ is new

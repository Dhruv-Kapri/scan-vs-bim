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


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_mapping_has_identifiers_only():
    """Cheap guard for the licence rule: the committed mapping holds no factor values."""
    columns = list(read(MAPPING)[0])
    assert columns == ["ifc_material", "oekobaudat_uuid", "basis", "dataset_name", "note"]
    for r in read(MAPPING):
        assert r["basis"] in ("", "volume", "opening_area")
        assert bool(r["oekobaudat_uuid"]) == bool(r["basis"]) == bool(r["dataset_name"])  # a mapped material has all three, an unmapped one none


def test_notebook_04b_carbon_table_adds_up(tmp_path):
    """One row per room element in carbon_elements.csv; confirmed + rest = total; every mapped dataset is used or reported;
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

    for variant, column in (("no_labels", "verdict_no_labels"), ("oracle_labels", "verdict_oracle_labels")):
        kg = {r["global_id"]: float(r["kg_co2e_a1_a3"]) for r in elements}
        assert all(r[column] == verdicts[variant][r["global_id"]] for r in elements)
        confirmed = sum(v for g, v in kg.items() if verdicts[variant][g] in ("OK", "shifted"))
        rest = sum(v for g, v in kg.items() if verdicts[variant][g] not in ("OK", "shifted"))
        assert confirmed + rest == pytest.approx(sum(kg.values()))

    assert sum(float(r["kg_co2e_a1_a3"] or 0) for r in layers) == pytest.approx(sum(float(r["kg_co2e_a1_a3"]) for r in elements), abs=0.05 * len(elements))
    assert {r["status"] for r in layers} <= {"counted", "unmapped", "not quantifiable"}
    mapped = {r["oekobaudat_uuid"] for r in read(MAPPING) if r["oekobaudat_uuid"]}
    assert mapped <= {r["oekobaudat_uuid"] for r in layers}  # each mapped dataset is counted or reported as not quantifiable

    assert {p.name for p in tmp_path.iterdir()} == {"data", "notebooks", "outputs"}
    assert {p.name for p in (tmp_path / "outputs").iterdir()} == {"03a", "04b"}  # only outputs/04b/ is new

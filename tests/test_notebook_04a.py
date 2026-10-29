import csv
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element
import pytest

from run_notebook import run_notebook

ROOT = Path(__file__).parents[1]
NOTEBOOK = ROOT / "notebooks" / "04a_report.ipynb"
IFC = ROOT / "data" / "cras" / "craslabbim.ifc"
CSVS = {v: ROOT / "outputs" / "03a" / f"verdicts_{v}.csv" for v in ("no_labels", "oracle_labels")}


def read(path):
    with open(path, newline="") as f:
        return {r["global_id"]: r for r in csv.DictReader(f)}


def test_notebook_04a_writes_verdicts_into_ifc_and_bcf(tmp_path):
    """Known answers are asserted inside 04a; here: the IFC copy re-opens with the pset on exactly the 35 room elements,
    the BCF holds one topic per non-OK (no-labels) element, and only outputs/04a/ is new."""
    for p in [IFC, *CSVS.values()]:
        if not p.exists():
            pytest.skip(f"{p.relative_to(ROOT)} missing (download the data; run notebook 03a)")
    # Run a copy so the committed notebook is not rewritten and its outputs land in tmp_path, not the real outputs/.
    (tmp_path / "notebooks").mkdir()
    (tmp_path / "outputs" / "03a").mkdir(parents=True)
    (tmp_path / "data").symlink_to(ROOT / "data")
    for p in CSVS.values():
        shutil.copy(p, tmp_path / "outputs" / "03a")
    copy = shutil.copy(NOTEBOOK, tmp_path / "notebooks")
    run_notebook(Path(copy), timeout=1800)

    out = tmp_path / "outputs" / "04a"
    no_labels, oracle = read(CSVS["no_labels"]), read(CSVS["oracle_labels"])
    assert len(no_labels) == 35

    ifc = ifcopenshell.open(str(next(out.glob("*.ifc"))))
    assert ifc.schema == "IFC2X3"
    with_pset = set()
    for el in ifc.by_type("IfcElement"):
        props = ifcopenshell.util.element.get_psets(el).get("ScanVsBim_Verdict")
        if props is not None:
            with_pset.add(el.GlobalId)
            assert props["Verdict"] == no_labels[el.GlobalId]["verdict"]
            assert props["Verdict_OracleLabels"] == oracle[el.GlobalId]["verdict"]
    assert with_pset == set(no_labels)

    not_ok = {g for g, r in no_labels.items() if r["verdict"] != "OK"}
    with zipfile.ZipFile(next(out.glob("*.bcf"))) as z:
        assert ET.fromstring(z.read("bcf.version")).attrib["VersionId"] == "2.1"
        markups = [n for n in z.namelist() if n.endswith("markup.bcf")]
        selected = [c.attrib["IfcGuid"] for n in z.namelist() if n.endswith(".bcfv") for c in ET.fromstring(z.read(n)).iter("Component")]
    assert len(markups) == len(not_ok)
    assert set(selected) == not_ok

    assert {p.name for p in tmp_path.iterdir()} == {"data", "notebooks", "outputs"}
    assert {p.name for p in (tmp_path / "outputs").iterdir()} == {"03a", "04a"}  # only outputs/04a/ is new

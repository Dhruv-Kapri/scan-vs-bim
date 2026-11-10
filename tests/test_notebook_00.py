from pathlib import Path
from typing import cast

import ifcopenshell
import ifcopenshell.util.element
from run_notebook import run_notebook

NOTEBOOK = Path(__file__).parents[1] / "notebooks" / "00_pipeline_overview.ipynb"


def test_notebook_00_runs_with_known_answers() -> None:
    """The known answers (registration within the 05 gate, moved wall shifted, rest OK, BCF issue) are asserted inside 00;
    here: the report IFC has a verdict pset on all 7 elements and no duplicate GlobalIds (issue #19)."""
    run_notebook(NOTEBOOK)
    report = ifcopenshell.open(str(NOTEBOOK.parents[1] / "outputs" / "00" / "toy_room_verdicts.ifc"))
    ids = [e.GlobalId for e in report.by_type("IfcRoot")]
    assert len(ids) == len(set(ids))
    elements = report.by_type("IfcElement")
    assert len(elements) == 7
    assert all("ScanVsBim_Verdict" in ifcopenshell.util.element.get_psets(cast(ifcopenshell.entity_instance, e)) for e in elements)

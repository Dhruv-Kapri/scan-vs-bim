"""Read one ÖKOBAUDAT process dataset (ILCD+EPD XML) and its reference-flow dataset.

Gives the dataset's identity, its GWP-total A1-A3 per declared unit and how much kg / m3 / m2 one declared unit
holds, where the flow properties say so. Nothing is ever guessed: a missing conversion gives None.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass

NS = {
    "p": "http://lca.jrc.it/ILCD/Process",
    "f": "http://lca.jrc.it/ILCD/Flow",
    "c": "http://lca.jrc.it/ILCD/Common",
    "e": "http://www.iai.kit.edu/EPD/2013",
}
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
EPD_MODULE = "{%s}module" % NS["e"]
# LCIA method datasets for the total climate indicator: EN 15804+A2 "GWP-total", and EF 3.1's "Climate change"
GWP_TOTAL_METHODS = {"6a37f984-a4b3-458a-a20a-64418c145fa2", "a7ea142a-9749-11ed-a8fc-0242ac120002"}
# ILCD flow property datasets, by UUID (the display names are translated: "Area" / "Fläche")
UNIT_OF_PROPERTY = {
    "93a60a56-a3c8-19da-a746-0800200c9a66": "m2",
    "93a60a56-a3c8-22da-a746-0800200c9a66": "m3",
    "93a60a56-a3c8-11da-a746-0800200b9a66": "kg",
}


@dataclass(frozen=True)
class Dataset:
    uuid: str
    version: str
    name: str  # English
    declared_unit: str  # "m2", "m3", "kg", or "other"
    gwp_a1_a3: float  # kg CO2e per declared unit, product stage
    per_declared_unit: dict[str, float]  # how many m2 / m3 / kg one declared unit holds (only those the flow gives)

    def carbon(self, quantities: dict[str, float]) -> float | None:
        """kg CO2e (A1-A3) for the given quantities ({"m3": ..., "m2": ...}), or None if none converts to the declared unit."""
        for unit, amount in quantities.items():
            if unit in self.per_declared_unit:
                return self.gwp_a1_a3 * amount / self.per_declared_unit[unit]
        return None


def reference_flow_uuid(process_xml: str) -> str:
    root = ET.fromstring(process_xml)
    internal_id = root.findtext("p:processInformation/p:quantitativeReference/p:referenceToReferenceFlow", namespaces=NS)
    for exchange in root.iterfind("p:exchanges/p:exchange", NS):
        if exchange.get("dataSetInternalID") == internal_id:
            return exchange.find("p:referenceToFlowDataSet", NS).get("refObjectId")
    raise ValueError(f"reference flow {internal_id} not among the exchanges")


def _gwp_total_a1_a3(root: ET.Element) -> float:
    for result in root.iterfind("p:LCIAResults/p:LCIAResult", NS):
        if result.find("p:referenceToLCIAMethodDataSet", NS).get("refObjectId") in GWP_TOTAL_METHODS:
            amounts = {a.get(EPD_MODULE): float(a.text) for a in result.iter("{%s}amount" % NS["e"])}
            if "A1-A3" in amounts:
                return amounts["A1-A3"]
            if {"A1", "A2", "A3"} <= amounts.keys():
                return amounts["A1"] + amounts["A2"] + amounts["A3"]
    raise ValueError("no GWP-total A1-A3 result in the dataset")


def parse_dataset(process_xml: str, flow_xml: str) -> Dataset:
    root = ET.fromstring(process_xml)
    name = next(n.text for n in root.iterfind("p:processInformation/p:dataSetInformation/p:name/p:baseName", NS) if n.get(XML_LANG) == "en")
    flow = ET.fromstring(flow_xml)
    reference = flow.findtext("f:flowInformation/f:quantitativeReference/f:referenceToReferenceFlowProperty", namespaces=NS)
    per_unit, declared = {}, "other"
    for prop in flow.iterfind("f:flowProperties/f:flowProperty", NS):
        unit = UNIT_OF_PROPERTY.get(prop.find("f:referenceToFlowPropertyDataSet", NS).get("refObjectId"))
        if unit:
            per_unit[unit] = float(prop.findtext("f:meanValue", namespaces=NS))
        if prop.get("dataSetInternalID") == reference:
            declared = unit or "other"
    return Dataset(
        uuid=root.findtext("p:processInformation/p:dataSetInformation/c:UUID", namespaces=NS),
        version=root.findtext("p:administrativeInformation/p:publicationAndOwnership/c:dataSetVersion", namespaces=NS),
        name=name,
        declared_unit=declared,
        gwp_a1_a3=_gwp_total_a1_a3(root),
        per_declared_unit=per_unit,
    )

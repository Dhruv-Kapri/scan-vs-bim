"""Parser tests on small synthetic ILCD-shaped XML; every number here is invented."""

import pytest

from scan_vs_bim.oekobaudat import parse_dataset, reference_flow_uuid

GWP_TOTAL_A2 = "6a37f984-a4b3-458a-a20a-64418c145fa2"  # EN 15804+A2 "GWP-total"
GWP_FOSSIL_A2 = "5f635281-343e-44fb-83df-1971b155e6b6"
CLIMATE_CHANGE_EF31 = "a7ea142a-9749-11ed-a8fc-0242ac120002"  # EF 3.1 "Climate change" (= total)
AREA, MASS, VOLUME = (f"93a60a56-a3c8-{x}-a746-0800200{y}" for x, y in (("19da", "c9a66"), ("11da", "b9a66"), ("22da", "c9a66")))


def process(uuid="p-1", flow="f-1", results=(), version="01.02.003"):
    """results: (method uuid, {module: amount}) pairs."""
    lcia = "".join(
        f'<LCIAResult><referenceToLCIAMethodDataSet refObjectId="{m}"/><common:other>'
        + "".join(f'<epd:amount epd:module="{mod}">{v}</epd:amount>' for mod, v in amounts.items())
        + "</common:other></LCIAResult>"
        for m, amounts in results
    )
    return f"""<processDataSet xmlns="http://lca.jrc.it/ILCD/Process" xmlns:common="http://lca.jrc.it/ILCD/Common"
        xmlns:epd="http://www.iai.kit.edu/EPD/2013">
      <processInformation><dataSetInformation><common:UUID>{uuid}</common:UUID>
        <name><baseName xml:lang="de">Testdaten</baseName><baseName xml:lang="en">Test material</baseName></name>
        </dataSetInformation>
        <quantitativeReference><referenceToReferenceFlow>7</referenceToReferenceFlow></quantitativeReference>
      </processInformation>
      <administrativeInformation><publicationAndOwnership><common:dataSetVersion>{version}</common:dataSetVersion>
        </publicationAndOwnership></administrativeInformation>
      <exchanges><exchange dataSetInternalID="3"><referenceToFlowDataSet refObjectId="other"/></exchange>
        <exchange dataSetInternalID="7"><referenceToFlowDataSet refObjectId="{flow}"/></exchange></exchanges>
      <LCIAResults>{lcia}</LCIAResults></processDataSet>"""


def flow(reference, properties):
    """reference: property uuid; properties: {property uuid: amount per one reference unit}."""
    ids = list(properties)
    body = "".join(
        f'<flowProperty dataSetInternalID="{i}"><referenceToFlowPropertyDataSet refObjectId="{p}"/>'
        f"<meanValue>{v}</meanValue></flowProperty>"
        for i, (p, v) in enumerate(properties.items())
    )
    return f"""<flowDataSet xmlns="http://lca.jrc.it/ILCD/Flow" xmlns:common="http://lca.jrc.it/ILCD/Common">
      <flowInformation><quantitativeReference><referenceToReferenceFlowProperty>{ids.index(reference)}</referenceToReferenceFlowProperty>
        </quantitativeReference></flowInformation><flowProperties>{body}</flowProperties></flowDataSet>"""


def test_reads_identity_declared_unit_and_combined_a1_a3():
    p = process(results=[(GWP_TOTAL_A2, {"A1-A3": 12.5, "C2": 99})])
    d = parse_dataset(p, flow(VOLUME, {VOLUME: 1}))
    assert (d.uuid, d.version, d.name) == ("p-1", "01.02.003", "Test material")
    assert d.declared_unit == "m3"
    assert d.gwp_a1_a3 == 12.5  # not the C2 module


def test_split_modules_are_summed():
    p = process(results=[(GWP_TOTAL_A2, {"A1": 1.5, "A2": 2.0, "A3": 0.25, "C2": 99})])
    assert parse_dataset(p, flow(AREA, {AREA: 1})).gwp_a1_a3 == 3.75


def test_picks_the_total_climate_indicator_in_either_method_version():
    for total in (GWP_TOTAL_A2, CLIMATE_CHANGE_EF31):
        p = process(results=[(GWP_FOSSIL_A2, {"A1-A3": 1}), (total, {"A1-A3": 7})])
        assert parse_dataset(p, flow(MASS, {MASS: 1})).gwp_a1_a3 == 7


def test_no_total_climate_indicator_is_an_error():
    with pytest.raises(ValueError, match="GWP-total"):
        parse_dataset(process(results=[(GWP_FOSSIL_A2, {"A1-A3": 1})]), flow(MASS, {MASS: 1}))


def test_conversions_come_from_the_flow_properties():
    p = process(results=[(GWP_TOTAL_A2, {"A1-A3": 10})])
    d = parse_dataset(p, flow(VOLUME, {VOLUME: 1, MASS: 800}))
    assert d.per_declared_unit == {"m3": 1, "kg": 800}  # one m3 holds 800 kg; no area given


def test_reference_flow_uuid_follows_the_internal_id():
    assert reference_flow_uuid(process(flow="f-42")) == "f-42"


def dataset(reference, properties):
    return parse_dataset(process(results=[(GWP_TOTAL_A2, {"A1-A3": 4})]), flow(reference, properties))


def test_carbon_in_the_declared_unit():
    assert dataset(VOLUME, {VOLUME: 1}).carbon({"m2": 5.0, "m3": 2.0}) == 8.0  # 2 m3 x 4


def test_carbon_converts_through_the_flow_properties():
    d = dataset(VOLUME, {VOLUME: 1, MASS: 800})
    assert d.carbon({"kg": 1600.0}) == 8.0  # 1600 kg = 2 m3


def test_carbon_is_none_when_nothing_converts():
    assert dataset(MASS, {MASS: 1}).carbon({"m3": 2.0}) is None  # no density in the data: never guessed


def test_a_total_indicator_without_a1_a3_is_skipped():
    p = process(results=[(GWP_TOTAL_A2, {"C2": 5}), (CLIMATE_CHANGE_EF31, {"A1": 1, "A2": 1})])
    with pytest.raises(ValueError, match="GWP-total"):
        parse_dataset(p, flow(MASS, {MASS: 1}))

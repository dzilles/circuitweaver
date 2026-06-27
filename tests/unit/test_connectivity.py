"""Tests for canonical source-connectivity planning."""

from pathlib import Path

import pytest

from circuitweaver.compiler.connectivity import (
    build_connection_plan,
    build_logical_nets,
    build_sheet_connectivity,
)
from circuitweaver.compiler.engine import CompileEngine
from circuitweaver.compiler.global_nets import GlobalNetResolver
from circuitweaver.io.json import read_circuit
from circuitweaver.transform.source_to_layout import SourceToLayoutTransform
from circuitweaver.types import (
    Point,
    SchematicHierarchicalLabel,
    SchematicHierarchicalPin,
    SchematicNetLabel,
    SheetConnection,
    SourceComponent,
    SourceGroup,
    SourceNet,
    SourcePort,
    SourceTrace,
)


@pytest.mark.parametrize(
    ("net", "expected_label"),
    [
        (SourceNet(source_net_id="VCC", name="VCC", is_power=True), "VCC"),
        (SourceNet(source_net_id="GND", name="GND", is_ground=True), "GND"),
    ],
)
def test_single_port_power_or_ground_net_renders_as_global_label(net, expected_label):
    port = SourcePort(source_port_id="P1", source_component_id="U1", name="1")
    trace = SourceTrace(
        source_trace_id="T1",
        connected_source_port_ids=["P1"],
        connected_source_net_ids=[net.source_net_id],
    )

    generated, sheet_connectivity = build_sheet_connectivity(
        traces=[trace],
        ports=[port],
        nets=[net],
        element_to_sheet={"P1": "root"},
        element_to_group={"U1": "root"},
        groups=[],
        elements=[net],
        global_resolver=GlobalNetResolver.from_elements([net]),
    )

    assert generated == []
    assert sheet_connectivity["root"][0]["render_kind"] == "global_label"
    assert sheet_connectivity["root"][0]["ports"] == ["P1"]
    assert sheet_connectivity["root"][0]["label_text"] == expected_label


def test_traces_with_same_source_net_merge_into_one_logical_net_and_connection():
    net = SourceNet(source_net_id="N1", name="SIG")
    ports = [
        SourcePort(source_port_id="P1", source_component_id="U1", name="1"),
        SourcePort(source_port_id="P2", source_component_id="U2", name="1"),
    ]
    traces = [
        SourceTrace(
            source_trace_id="T1",
            connected_source_port_ids=["P1"],
            connected_source_net_ids=["N1"],
        ),
        SourceTrace(
            source_trace_id="T2",
            connected_source_port_ids=["P2"],
            connected_source_net_ids=["N1"],
        ),
    ]

    logical_nets = build_logical_nets(
        traces=traces,
        ports=ports,
        nets=[net],
        element_to_sheet={"P1": "root", "P2": "root"},
        element_to_group={"U1": "root", "U2": "root"},
        global_resolver=GlobalNetResolver.from_elements([net]),
    )
    _, sheet_connectivity = build_sheet_connectivity(
        traces=traces,
        ports=ports,
        nets=[net],
        element_to_sheet={"P1": "root", "P2": "root"},
        element_to_group={"U1": "root", "U2": "root"},
        groups=[],
        elements=[net],
        global_resolver=GlobalNetResolver.from_elements([net]),
    )

    assert len(logical_nets) == 1
    assert set(logical_nets[0].source_trace_ids) == {"T1", "T2"}
    assert len(sheet_connectivity["root"]) == 1
    assert sheet_connectivity["root"][0]["render_kind"] == "wire"
    assert set(sheet_connectivity["root"][0]["ports"]) == {"P1", "P2"}


def test_direct_two_port_trace_without_source_net_remains_wire_rendered():
    ports = [
        SourcePort(source_port_id="P1", source_component_id="U1", name="1"),
        SourcePort(source_port_id="P2", source_component_id="U2", name="1"),
    ]
    trace = SourceTrace(source_trace_id="T1", connected_source_port_ids=["P1", "P2"])

    _, sheet_connectivity = build_sheet_connectivity(
        traces=[trace],
        ports=ports,
        nets=[],
        element_to_sheet={"P1": "root", "P2": "root"},
        element_to_group={"U1": "root", "U2": "root"},
        groups=[],
        elements=[],
        global_resolver=GlobalNetResolver.from_elements([]),
    )

    assert sheet_connectivity["root"][0]["render_kind"] == "wire"


def test_connection_plan_returns_typed_sheet_connections_with_legacy_adapter():
    ports = [
        SourcePort(source_port_id="P1", source_component_id="U1", name="1"),
        SourcePort(source_port_id="P2", source_component_id="U2", name="1"),
    ]
    trace = SourceTrace(source_trace_id="T1", connected_source_port_ids=["P1", "P2"])

    _, plan = build_connection_plan(
        traces=[trace],
        ports=ports,
        nets=[],
        element_to_sheet={"P1": "root", "P2": "root"},
        element_to_group={"U1": "root", "U2": "root"},
        groups=[],
        elements=[],
        global_resolver=GlobalNetResolver.from_elements([]),
    )
    _, legacy = build_sheet_connectivity(
        traces=[trace],
        ports=ports,
        nets=[],
        element_to_sheet={"P1": "root", "P2": "root"},
        element_to_group={"U1": "root", "U2": "root"},
        groups=[],
        elements=[],
        global_resolver=GlobalNetResolver.from_elements([]),
    )

    connection = plan["root"][0]
    assert isinstance(connection, SheetConnection)
    assert connection.trace_id == "T1"
    assert connection.render_kind == "wire"
    assert connection.endpoint_port_ids == ("P1", "P2")
    assert legacy["root"][0] == connection.to_legacy_dict()


def test_source_to_layout_consumes_typed_sheet_connection():
    elements = [
        SourceComponent(source_component_id="U1", name="U1"),
        SourceComponent(source_component_id="U2", name="U2"),
        SourcePort(source_port_id="P1", source_component_id="U1", name="1"),
        SourcePort(source_port_id="P2", source_component_id="U2", name="1"),
    ]
    connection = SheetConnection(
        net_id="T1",
        trace_ids=("T1",),
        sheet_id="root",
        endpoint_port_ids=("P1", "P2"),
        render_kind="wire",
        label_text="NET_T1",
        hierarchical_label_text="HPIN_T1",
    )

    layout, _ = SourceToLayoutTransform().transform(
        "root",
        elements,
        sheet_connectivity={"root": [connection]},
    )

    assert any(edge.id == "e_T1_P2" for edge in layout.edges)


def test_source_to_layout_converts_legacy_dicts_at_boundary():
    elements = [
        SourceComponent(source_component_id="U1", name="U1"),
        SourcePort(source_port_id="P1", source_component_id="U1", name="1"),
    ]
    legacy_connection = {
        "trace_id": "T1",
        "net_id": "N1",
        "ports": ["P1"],
        "is_global_net": True,
        "label_text": "VCC",
    }

    _, registry = SourceToLayoutTransform().transform(
        "root",
        elements,
        sheet_connectivity={"root": [legacy_connection]},
    )

    labels = [
        element
        for element in registry.layout_to_element.values()
        if isinstance(element, SchematicNetLabel)
    ]
    assert labels[0].text == "VCC"
    assert labels[0].is_global is True


def test_non_global_inter_sheet_net_creates_hierarchical_pin_plans():
    groups = [
        SourceGroup(source_group_id="sheet_a", is_subcircuit=True),
        SourceGroup(source_group_id="sheet_b", is_subcircuit=True),
    ]
    net = SourceNet(source_net_id="N1", name="SIG")
    ports = [
        SourcePort(source_port_id="P1", source_component_id="U1", name="OUT"),
        SourcePort(source_port_id="P2", source_component_id="U2", name="IN"),
    ]
    trace = SourceTrace(
        source_trace_id="T1",
        connected_source_port_ids=["P1", "P2"],
        connected_source_net_ids=["N1"],
    )

    generated, sheet_connectivity = build_sheet_connectivity(
        traces=[trace],
        ports=ports,
        nets=[net],
        element_to_sheet={"P1": "sheet_a", "P2": "sheet_b", "sheet_a": "root", "sheet_b": "root"},
        element_to_group={"U1": "sheet_a", "U2": "sheet_b"},
        groups=groups,
        elements=[*groups, net],
        global_resolver=GlobalNetResolver.from_elements([net]),
    )

    assert {pin.schematic_box_id for pin in generated if isinstance(pin, SchematicHierarchicalPin)} == {
        "box_sheet_a",
        "box_sheet_b",
    }
    assert sheet_connectivity["sheet_a"][0]["render_kind"] == "hierarchical_label"
    assert sheet_connectivity["sheet_b"][0]["render_kind"] == "hierarchical_label"


def test_nested_child_to_parent_net_stops_at_parent_sheet():
    groups = [
        SourceGroup(source_group_id="parent", is_subcircuit=True),
        SourceGroup(
            source_group_id="child",
            parent_source_group_id="parent",
            is_subcircuit=True,
        ),
    ]
    net = SourceNet(source_net_id="N1", name="SIG")
    ports = [
        SourcePort(source_port_id="P_CHILD", source_component_id="U_CHILD", name="OUT"),
        SourcePort(source_port_id="P_PARENT", source_component_id="U_PARENT", name="IN"),
    ]
    trace = SourceTrace(
        source_trace_id="T1",
        connected_source_port_ids=["P_CHILD", "P_PARENT"],
        connected_source_net_ids=["N1"],
    )

    generated, sheet_connectivity = build_connection_plan(
        traces=[trace],
        ports=ports,
        nets=[net],
        element_to_sheet={
            "P_CHILD": "child",
            "P_PARENT": "parent",
            "parent": "root",
            "child": "parent",
        },
        element_to_group={"U_CHILD": "child", "U_PARENT": "parent"},
        groups=groups,
        elements=[*groups, net],
        global_resolver=GlobalNetResolver.from_elements([net]),
    )

    hpins = [element for element in generated if isinstance(element, SchematicHierarchicalPin)]
    labels = [element for element in generated if isinstance(element, SchematicNetLabel)]

    assert [(pin.schematic_box_id, pin.sheet_id) for pin in hpins] == [("box_child", "parent")]
    assert {label.sheet_id for label in labels} == {"parent"}
    assert sheet_connectivity["child"][0].render_kind == "hierarchical_label"
    assert sheet_connectivity["parent"][0].render_kind == "local_label"
    assert sheet_connectivity["parent"][0].label_text == "HPIN_SIG"


def test_nested_branch_to_branch_net_creates_intermediate_bridge_connections():
    groups = [
        SourceGroup(source_group_id="parent_left", is_subcircuit=True),
        SourceGroup(
            source_group_id="child_left",
            parent_source_group_id="parent_left",
            is_subcircuit=True,
        ),
        SourceGroup(source_group_id="parent_right", is_subcircuit=True),
        SourceGroup(
            source_group_id="child_right",
            parent_source_group_id="parent_right",
            is_subcircuit=True,
        ),
    ]
    net = SourceNet(source_net_id="N1", name="SIG")
    ports = [
        SourcePort(source_port_id="P_LEFT", source_component_id="U_LEFT", name="OUT"),
        SourcePort(source_port_id="P_RIGHT", source_component_id="U_RIGHT", name="IN"),
    ]
    trace = SourceTrace(
        source_trace_id="T1",
        connected_source_port_ids=["P_LEFT", "P_RIGHT"],
        connected_source_net_ids=["N1"],
    )

    generated, sheet_connectivity = build_connection_plan(
        traces=[trace],
        ports=ports,
        nets=[net],
        element_to_sheet={
            "P_LEFT": "child_left",
            "P_RIGHT": "child_right",
            "parent_left": "root",
            "child_left": "parent_left",
            "parent_right": "root",
            "child_right": "parent_right",
        },
        element_to_group={"U_LEFT": "child_left", "U_RIGHT": "child_right"},
        groups=groups,
        elements=[*groups, net],
        global_resolver=GlobalNetResolver.from_elements([net]),
    )

    hpins = [element for element in generated if isinstance(element, SchematicHierarchicalPin)]
    assert {(pin.schematic_box_id, pin.sheet_id) for pin in hpins} == {
        ("box_child_left", "parent_left"),
        ("box_parent_left", "root"),
        ("box_child_right", "parent_right"),
        ("box_parent_right", "root"),
    }
    assert sheet_connectivity["parent_left"][0].endpoint_port_ids == ("hpin_N1_child_left",)
    assert sheet_connectivity["parent_left"][0].render_kind == "hierarchical_label"
    assert sheet_connectivity["parent_right"][0].endpoint_port_ids == ("hpin_N1_child_right",)
    assert sheet_connectivity["parent_right"][0].render_kind == "hierarchical_label"


def test_source_to_layout_creates_bridge_hierarchical_label_from_hierarchical_pin():
    elements = [
        SourceGroup(source_group_id="child", is_subcircuit=True),
        SchematicHierarchicalPin(
            schematic_hierarchical_pin_id="hpin_N1_child",
            source_net_id="N1",
            schematic_box_id="box_child",
            sheet_id="parent",
            center=Point(x=0, y=0),
            text="HPIN_SIG",
        ),
    ]
    bridge_connection = SheetConnection(
        net_id="N1",
        trace_ids=("T1",),
        sheet_id="parent",
        endpoint_port_ids=("hpin_N1_child",),
        render_kind="hierarchical_label",
        label_text="HPIN_SIG",
        hierarchical_label_text="HPIN_SIG",
        source_net_id="N1",
        hierarchical_pin_id="hpin_N1_child",
        is_inter_sheet=True,
    )

    _, registry = SourceToLayoutTransform().transform(
        "parent",
        elements,
        sheet_connectivity={"parent": [bridge_connection]},
    )

    labels = [
        element
        for element in registry.layout_to_element.values()
        if isinstance(element, SchematicHierarchicalLabel)
    ]
    assert labels[0].text == "HPIN_SIG"
    assert labels[0].source_port_id == "hpin_N1_child"


def test_global_inter_sheet_net_uses_global_labels_without_hierarchical_pins():
    groups = [
        SourceGroup(source_group_id="sheet_a", is_subcircuit=True),
        SourceGroup(source_group_id="sheet_b", is_subcircuit=True),
    ]
    net = SourceNet(source_net_id="RET", name="RET", is_global=True)
    ports = [
        SourcePort(source_port_id="P1", source_component_id="U1", name="RET"),
        SourcePort(source_port_id="P2", source_component_id="U2", name="RET"),
    ]
    trace = SourceTrace(
        source_trace_id="T1",
        connected_source_port_ids=["P1", "P2"],
        connected_source_net_ids=["RET"],
    )

    generated, sheet_connectivity = build_sheet_connectivity(
        traces=[trace],
        ports=ports,
        nets=[net],
        element_to_sheet={"P1": "sheet_a", "P2": "sheet_b", "sheet_a": "root", "sheet_b": "root"},
        element_to_group={"U1": "sheet_a", "U2": "sheet_b"},
        groups=groups,
        elements=[*groups, net],
        global_resolver=GlobalNetResolver.from_elements([net]),
    )

    assert not any(isinstance(element, SchematicHierarchicalPin) for element in generated)
    assert sheet_connectivity["sheet_a"][0]["render_kind"] == "global_label"
    assert sheet_connectivity["sheet_b"][0]["render_kind"] == "global_label"


def test_simple_led_example_compiles_vcc_and_gnd_labels(tmp_path):
    elements = read_circuit(Path("examples/simple_led/circuit.json"))
    root = CompileEngine().compile(elements, tmp_path, project_name="demo")
    text = root.read_text(encoding="utf-8")

    assert text.count("(global_label") >= 2
    assert "VCC" in text
    assert "GND" in text

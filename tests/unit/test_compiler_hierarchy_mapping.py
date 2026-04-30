from circuitweaver.compiler.engine import CompileEngine
from circuitweaver.compiler.global_nets import GlobalNetResolver
from circuitweaver.types import (
    SchematicNetLabel,
    SchematicHierarchicalPin,
    SourceComponent,
    SourceGroup,
    SourceNet,
    SourcePort,
    SourceTrace,
)


def test_subcircuit_group_source_group_id_owns_sheet_when_subcircuit_id_is_omitted():
    engine = CompileEngine()
    group = SourceGroup(
        source_group_id="stm32_controller",
        name="STM32 Controller",
        is_subcircuit=True,
    )
    component = SourceComponent(
        source_component_id="U1",
        name="STM32",
        subcircuit_id="stm32_controller",
    )
    port = SourcePort(
        source_port_id="U1-1",
        source_component_id="U1",
        name="VBAT",
    )

    element_to_sheet, element_to_group = engine._map_elements(
        components=[component],
        groups=[group],
        ports=[port],
    )

    assert element_to_sheet["U1"] == "stm32_controller"
    assert element_to_sheet["U1-1"] == "stm32_controller"
    assert element_to_group["U1"] == "stm32_controller"
    assert element_to_sheet["stm32_controller"] == "root"


def test_explicit_subcircuit_id_remains_the_owned_sheet_id():
    engine = CompileEngine()
    group = SourceGroup(
        source_group_id="controller_group",
        subcircuit_id="stm32_controller",
        name="STM32 Controller",
        is_subcircuit=True,
    )
    component = SourceComponent(
        source_component_id="U1",
        name="STM32",
        subcircuit_id="stm32_controller",
    )

    element_to_sheet, element_to_group = engine._map_elements(
        components=[component],
        groups=[group],
        ports=[],
    )

    assert element_to_sheet["U1"] == "stm32_controller"
    assert element_to_group["U1"] == "controller_group"
    assert element_to_sheet["controller_group"] == "root"


def test_non_global_inter_sheet_net_generates_root_labels_for_hierarchical_pins():
    engine = CompileEngine()
    elements = [
        SourceGroup(source_group_id="sheet_a", is_subcircuit=True),
        SourceGroup(source_group_id="sheet_b", is_subcircuit=True),
        SourceComponent(source_component_id="U1", name="U1", subcircuit_id="sheet_a"),
        SourceComponent(source_component_id="U2", name="U2", subcircuit_id="sheet_b"),
        SourcePort(source_port_id="U1-1", source_component_id="U1", name="OUT"),
        SourcePort(source_port_id="U2-1", source_component_id="U2", name="IN"),
        SourceNet(source_net_id="SIG_A", name="SIG_A"),
        SourceTrace(
            source_trace_id="SIG_A_TRACE",
            connected_source_port_ids=["U1-1", "U2-1"],
            connected_source_net_ids=["SIG_A"],
        ),
    ]
    components = [e for e in elements if isinstance(e, SourceComponent)]
    groups = [e for e in elements if isinstance(e, SourceGroup)]
    ports = [e for e in elements if isinstance(e, SourcePort)]
    traces = [e for e in elements if isinstance(e, SourceTrace)]
    nets = [e for e in elements if isinstance(e, SourceNet)]
    element_to_sheet, element_to_group = engine._map_elements(components, groups, ports)

    generated, sheet_connectivity = engine._process_connectivity(
        traces,
        ports,
        nets,
        element_to_sheet,
        element_to_group,
        groups,
        elements,
        GlobalNetResolver.from_elements(elements),
    )

    hpins = [e for e in generated if isinstance(e, SchematicHierarchicalPin)]
    root_labels = [e for e in generated if isinstance(e, SchematicNetLabel) and e.sheet_id == "root"]

    assert {p.schematic_box_id for p in hpins} == {"box_sheet_a", "box_sheet_b"}
    assert {label.schematic_hierarchical_pin_id for label in root_labels} == {
        "hpin_SIG_A_sheet_a",
        "hpin_SIG_A_sheet_b",
    }
    assert {label.text for label in root_labels} == {"HPIN_SIG_A"}
    assert "root" not in sheet_connectivity


def test_explicit_global_inter_sheet_net_uses_global_label_connectivity_without_hierarchical_pins():
    engine = CompileEngine()
    elements = [
        SourceGroup(source_group_id="sheet_a", is_subcircuit=True),
        SourceGroup(source_group_id="sheet_b", is_subcircuit=True),
        SourceComponent(source_component_id="U1", name="U1", subcircuit_id="sheet_a"),
        SourceComponent(source_component_id="U2", name="U2", subcircuit_id="sheet_b"),
        SourcePort(source_port_id="U1-1", source_component_id="U1", name="GND"),
        SourcePort(source_port_id="U2-1", source_component_id="U2", name="GND"),
        SourceNet(source_net_id="RET", name="RET", is_global=True),
        SourceTrace(
            source_trace_id="RET_TRACE",
            connected_source_port_ids=["U1-1", "U2-1"],
            connected_source_net_ids=["RET"],
        ),
    ]
    components = [e for e in elements if isinstance(e, SourceComponent)]
    groups = [e for e in elements if isinstance(e, SourceGroup)]
    ports = [e for e in elements if isinstance(e, SourcePort)]
    traces = [e for e in elements if isinstance(e, SourceTrace)]
    nets = [e for e in elements if isinstance(e, SourceNet)]
    element_to_sheet, element_to_group = engine._map_elements(components, groups, ports)

    generated, sheet_connectivity = engine._process_connectivity(
        traces,
        ports,
        nets,
        element_to_sheet,
        element_to_group,
        groups,
        elements,
        GlobalNetResolver.from_elements(elements),
    )

    assert not any(isinstance(e, SchematicHierarchicalPin) for e in generated)
    for sheet_id in ("sheet_a", "sheet_b"):
        conn = sheet_connectivity[sheet_id][0]
        assert conn["is_inter_sheet"] is True
        assert conn["is_global_net"] is True
        assert conn["label_text"] == "RET"
        assert conn["hpin_id"] is None

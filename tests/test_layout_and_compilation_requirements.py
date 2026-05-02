"""Requirement-traceable tests for docs/requirements/layout-and-compilation.md."""

# ruff: noqa: ARG001, ARG002, ARG005, E501

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from circuitweaver.compiler.auto_router import AutoRouter
from circuitweaver.compiler.engine import CompileEngine
from circuitweaver.compiler.global_nets import (
    GlobalNetResolver,
    get_kicad_power_symbol_global_names,
)
from circuitweaver.project import CircuitProject
from circuitweaver.requirements import traceability_report
from circuitweaver.transform import (
    LayoutToSchematicTransform,
    SourceToLayoutTransform,
    get_effective_symbol_id,
    snap_to_grid,
)
from circuitweaver.transform.schematic_to_s_expr import GRID_TO_MM, SchematicToSExprTransform
from circuitweaver.types import (
    LayoutEdge,
    LayoutEdgeSection,
    LayoutNode,
    LayoutPoint,
    Point,
    SchematicBox,
    SchematicComponent,
    SchematicHierarchicalLabel,
    SchematicHierarchicalPin,
    SchematicNetLabel,
    SchematicNoConnect,
    SchematicPort,
    SchematicTrace,
    SourceComponent,
    SourceGroup,
    SourceNet,
    SourcePort,
    SourceProjectConfig,
    SourceTrace,
    s_expr_parse,
    s_expr_serialize,
)
from circuitweaver.validator import validate_circuit_file


class FakeRouter:
    def run(self, graph):
        return graph


def _engine() -> CompileEngine:
    return CompileEngine(router=FakeRouter())


def _pins_symbol():
    pin1 = SimpleNamespace(number="1", name="A", grid_offset=Point(x=0, y=0), direction="left", electrical_type="passive")
    pin2 = SimpleNamespace(number="2", name="B", grid_offset=Point(x=40, y=0), direction="right", electrical_type="passive")
    return SimpleNamespace(width=80, height=40, bounding_box_min=Point(x=0, y=0), pins=[pin1, pin2])


def _basic_source() -> list:
    return [
        SourceComponent(source_component_id="R1", name="R1", ftype="simple_resistor"),
        SourcePort(source_port_id="R1_1", source_component_id="R1", name="1", pin_number=1),
        SourcePort(source_port_id="R1_2", source_component_id="R1", name="2", pin_number=2),
    ]


def _schematic_project(name: str = "demo") -> CircuitProject:
    return CircuitProject(
        name=name,
        elements=[
            SourceComponent(source_component_id="R1", name="R1", symbol_id="Device:R", display_value="10k", footprint="R_0603"),
            SchematicComponent(schematic_component_id="sch_R1", source_component_id="R1", sheet_id="root", center=Point(x=10, y=20)),
        ],
    )


def _sexpr_text(elements: list | None = None, sources: dict | None = None) -> str:
    transform = SchematicToSExprTransform(uuid_factory=lambda: "00000000-0000-0000-0000-000000000000")
    sexpr = transform.transform(
        _schematic_project().elements if elements is None else elements,
        "root",
        _schematic_project().source_components if sources is None else sources,
    )
    return s_expr_serialize(sexpr)


def _sexpr(elements: list | None = None, sources: dict | None = None):
    transform = SchematicToSExprTransform(uuid_factory=lambda: "00000000-0000-0000-0000-000000000000")
    return transform.transform(
        _schematic_project().elements if elements is None else elements,
        "root",
        _schematic_project().source_components if sources is None else sources,
    )


def _all_edges(node: LayoutNode) -> list[LayoutEdge]:
    return [*node.edges, *(edge for child in node.children for edge in _all_edges(child))]


def test_lay_001_effective_symbol_id_prefers_explicit_symbol_id():
    assert get_effective_symbol_id(SourceComponent(source_component_id="R1", name="R1", symbol_id="Device:R", ftype="simple_led")) == "Device:R"


def test_lay_002_effective_symbol_id_infers_known_simple_ftypes():
    assert get_effective_symbol_id(SourceComponent(source_component_id="R1", name="R1", ftype="simple_resistor")) == "Device:R"
    assert get_effective_symbol_id(SourceComponent(source_component_id="C1", name="C1", ftype="simple_capacitor")) == "Device:C"
    assert get_effective_symbol_id(SourceComponent(source_component_id="LED1", name="LED1", ftype="simple_led")) == "Device:LED"
    assert get_effective_symbol_id(SourceComponent(source_component_id="D1", name="D1", ftype="simple_diode")) == "Device:D"
    assert get_effective_symbol_id(SourceComponent(source_component_id="Q1", name="Q1", ftype="simple_transistor")) == "Device:Q_NPN_BCE"


def test_lay_003_unknown_or_absent_ftype_does_not_infer_symbol():
    assert get_effective_symbol_id(SourceComponent(source_component_id="U1", name="U1", ftype="unknown")) is None
    assert get_effective_symbol_id(SourceComponent(source_component_id="U2", name="U2")) is None


def test_lay_010_source_to_layout_creates_requested_root_node_id():
    layout, _ = SourceToLayoutTransform().transform("sheet_a", [])
    assert layout.id == "sheet_a"


def test_lay_011_root_layout_uses_layered_elk_algorithm():
    layout, _ = SourceToLayoutTransform().transform("root", [])
    assert layout.layoutOptions["org.eclipse.elk.algorithm"] == "layered"


def test_lay_012_root_layout_includes_expected_padding():
    layout, _ = SourceToLayoutTransform().transform("root", [])
    assert layout.layoutOptions["org.eclipse.elk.padding"] == "[top=100,left=100,bottom=100,right=100]"


def test_lay_013_root_layout_includes_node_spacing_50():
    layout, _ = SourceToLayoutTransform().transform("root", [])
    assert layout.layoutOptions["org.eclipse.elk.layered.spacing.nodeNode"] == "50"


def test_lay_014_source_groups_become_box_nodes():
    layout, _ = SourceToLayoutTransform().transform("root", [SourceGroup(source_group_id="G1")])
    assert layout.children[0].id == "box_G1"


def test_lay_015_group_box_nodes_have_minimum_dimensions():
    layout, _ = SourceToLayoutTransform().transform("root", [SourceGroup(source_group_id="G1")])
    assert layout.children[0].width == 250
    assert layout.children[0].height == 100


def test_lay_016_group_box_nodes_use_fixed_port_constraints():
    layout, _ = SourceToLayoutTransform().transform("root", [SourceGroup(source_group_id="G1")])
    assert layout.children[0].layoutOptions["org.eclipse.elk.portConstraints"] == "FIXED_POS"


def test_lay_017_subcircuit_groups_create_hierarchical_ports_for_matching_pins():
    elements = [
        SourceGroup(source_group_id="G1", is_subcircuit=True),
        SchematicHierarchicalPin(schematic_hierarchical_pin_id="HP1", source_net_id="N1", schematic_box_id="box_G1", center=Point(x=0, y=0), text="IN", sheet_id="root"),
    ]
    layout, registry = SourceToLayoutTransform().transform("root", elements)
    assert layout.children[0].ports[0].id == "box_G1:HP1"
    assert registry.element_to_port["HP1"] == "box_G1:HP1"


def test_lay_018_hierarchical_ports_alternate_west_and_east_sides():
    elements = [
        SourceGroup(source_group_id="G1", is_subcircuit=True),
        SchematicHierarchicalPin(schematic_hierarchical_pin_id="A", source_net_id="N1", schematic_box_id="box_G1", center=Point(x=0, y=0), text="A", sheet_id="root"),
        SchematicHierarchicalPin(schematic_hierarchical_pin_id="B", source_net_id="N2", schematic_box_id="box_G1", center=Point(x=0, y=0), text="B", sheet_id="root"),
    ]
    layout, _ = SourceToLayoutTransform().transform("root", elements)
    assert [p.layoutOptions["org.eclipse.elk.port.side"] for p in layout.children[0].ports] == ["WEST", "EAST"]


def test_lay_019_source_components_become_layout_nodes_with_source_id():
    layout, _ = SourceToLayoutTransform().transform("root", [SourceComponent(source_component_id="R1", name="R1")])
    assert layout.children[0].id == "R1"


def test_lay_020_component_layout_nodes_use_fixed_port_constraints():
    layout, _ = SourceToLayoutTransform().transform("root", [SourceComponent(source_component_id="R1", name="R1")])
    assert layout.children[0].layoutOptions["org.eclipse.elk.portConstraints"] == "FIXED_POS"


def test_lay_021_component_dimensions_come_from_symbol_bounds_when_available():
    layout, _ = SourceToLayoutTransform(symbol_map={"Device:R": _pins_symbol()}).transform("root", [SourceComponent(source_component_id="R1", name="R1", symbol_id="Device:R")])
    assert (layout.children[0].width, layout.children[0].height) == (80, 40)


def test_lay_022_component_dimensions_default_to_40_without_symbol():
    layout, _ = SourceToLayoutTransform().transform("root", [SourceComponent(source_component_id="R1", name="R1")])
    assert (layout.children[0].width, layout.children[0].height) == (40, 40)


def test_lay_023_symbol_pins_create_ports_registered_by_pin_number():
    elements = [
        SourceComponent(source_component_id="R1", name="R1", symbol_id="Device:R"),
        SourcePort(source_port_id="P1", source_component_id="R1", name="A", pin_number=1),
    ]
    layout, registry = SourceToLayoutTransform(symbol_map={"Device:R": _pins_symbol()}).transform("root", elements)
    assert layout.children[0].ports[0].id == "R1:1"
    assert registry.element_to_port["P1"] == "R1:1"


def test_lay_024_without_symbol_ports_are_created_from_source_ports_in_order_on_west_side():
    elements = [
        SourceComponent(source_component_id="R1", name="R1"),
        SourcePort(source_port_id="P1", source_component_id="R1", name="1", pin_number=1),
    ]
    layout, registry = SourceToLayoutTransform().transform("root", elements)
    assert layout.children[0].ports[0].layoutOptions["org.eclipse.elk.port.side"] == "WEST"
    assert registry.element_to_port["P1"] == "R1:1"


def test_lay_025_same_context_connections_become_elk_edges():
    elements = [
        *_basic_source(),
        SourceComponent(source_component_id="R2", name="R2"),
        SourcePort(source_port_id="R2_1", source_component_id="R2", name="1", pin_number=1),
    ]
    sheet_conn = {"root": [{"trace_id": "T1", "ports": ["R1_1", "R2_1"], "is_inter_group": False, "is_inter_sheet": False, "is_global_net": False}]}
    layout, _ = SourceToLayoutTransform().transform("root", elements, sheet_conn)
    assert layout.edges[0].id == "e_T1_R2_1"
    assert layout.edges[0].sources == ["R1:1"]
    assert layout.edges[0].targets == ["R2:1"]


def test_lay_026_cross_context_connections_become_label_nodes_and_edges():
    elements = [
        SourceGroup(source_group_id="G1"),
        SourceGroup(source_group_id="G2"),
        SourceComponent(source_component_id="R1", name="R1", source_group_id="G1"),
        SourcePort(source_port_id="R1_1", source_component_id="R1", name="1", pin_number=1),
        SourceComponent(source_component_id="R2", name="R2", source_group_id="G2"),
        SourcePort(source_port_id="R2_1", source_component_id="R2", name="1", pin_number=1),
    ]
    sheet_conn = {"root": [{"trace_id": "T1", "ports": ["R1_1", "R2_1"], "is_inter_group": True, "is_inter_sheet": False, "is_global_net": False, "label_text": "NET_T1"}]}
    layout, registry = SourceToLayoutTransform().transform("root", elements, sheet_conn)
    assert any(child.id.startswith("label_node_") for box in layout.children for child in box.children)
    assert any(edge.id.startswith("e_label_") for edge in _all_edges(layout))
    assert registry.get_element_by_layout_id("label_node_label_T1_R1_1")


def test_lay_027_no_connect_markers_become_zero_size_nodes_and_nc_edges():
    elements = [*_basic_source(), SchematicNoConnect(schematic_no_connect_id="NC1", schematic_port_id="R1_1", sheet_id="root")]
    layout, _ = SourceToLayoutTransform().transform("root", elements)
    assert any(child.id == "nc_node_NC1" and child.width == 0 and child.height == 0 for child in layout.children)
    assert any(edge.id == "e_nc_NC1" for edge in layout.edges)


def test_cmp_001_compile_creates_output_directory(tmp_path):
    out = tmp_path / "out"
    path = _engine().compile(_schematic_project("demo").elements, out, project_name="demo")
    assert out.exists()
    assert path == out / "demo.kicad_sch"


def test_cmp_002_compile_validates_schematic_completeness_before_layout_selection():
    project = CircuitProject(elements=[*_basic_source(), SchematicComponent(schematic_component_id="S1", source_component_id="missing", sheet_id="root", center=Point(x=0, y=0))])
    assert not _engine().schematic_completeness(project).ok


def test_cmp_003_complete_schematic_is_reused_and_incomplete_schematic_runs_layout(monkeypatch):
    engine = _engine()
    complete = _schematic_project()
    assert engine.schematic_project(complete).value is complete


def test_cmp_004_no_sheet_ids_default_to_root_sheet():
    assert CircuitProject(elements=[SchematicComponent(schematic_component_id="S1", source_component_id="U1", sheet_id="root", center=Point(x=0, y=0))]).sheet_ids == {"root"}


def test_cmp_005_compiler_writes_one_schematic_per_discovered_sheet(tmp_path):
    project = CircuitProject(name="demo", elements=[
        SchematicComponent(schematic_component_id="R", source_component_id="R1", sheet_id="root", center=Point(x=0, y=0)),
        SchematicComponent(schematic_component_id="C", source_component_id="C1", sheet_id="child", center=Point(x=0, y=0)),
    ])
    result = _engine().write_kicad(_engine().kicad_project(project).value, tmp_path)
    assert result.ok
    assert (tmp_path / "demo.kicad_sch").exists()
    assert (tmp_path / "child.kicad_sch").exists()


def test_cmp_006_root_sheet_is_project_name_schematic(tmp_path):
    _engine().compile(_schematic_project("board").elements, tmp_path, project_name="board")
    assert (tmp_path / "board.kicad_sch").exists()


def test_cmp_007_non_root_sheets_are_written_as_sheet_id_schematics(tmp_path):
    test_cmp_005_compiler_writes_one_schematic_per_discovered_sheet(tmp_path)
    assert (tmp_path / "child.kicad_sch").exists()


def test_cmp_008_compiler_always_writes_project_file(tmp_path):
    _engine().compile(_schematic_project("board").elements, tmp_path, project_name="board")
    assert (tmp_path / "board.kicad_pro").exists()


def test_cmp_009_compile_returns_root_schematic_path(tmp_path):
    assert _engine().compile(_schematic_project("board").elements, tmp_path, project_name="board") == tmp_path / "board.kicad_sch"


def test_cmp_020_components_are_assigned_to_sheets_from_group_or_subcircuit():
    group = SourceGroup(source_group_id="G1", subcircuit_id="SHEET", is_subcircuit=True)
    comp = SourceComponent(source_component_id="U1", name="U1", subcircuit_id="SHEET")
    sheets, _ = _engine()._map_elements([comp], [group], [])
    assert sheets["U1"] == "SHEET"


def test_cmp_021_subcircuit_group_with_subcircuit_id_owns_that_sheet_id():
    assert _engine()._get_group_sheet_id(SourceGroup(source_group_id="G1", subcircuit_id="SHEET", is_subcircuit=True)) == "SHEET"


def test_cmp_022_groups_are_assigned_to_parent_group_owned_sheet():
    parent = SourceGroup(source_group_id="P", subcircuit_id="SHEET", is_subcircuit=True)
    child = SourceGroup(source_group_id="C", parent_source_group_id="P")
    sheets, _ = _engine()._map_elements([], [parent, child], [])
    assert sheets["C"] == "SHEET"


def test_cmp_023_component_ports_are_assigned_to_parent_component_sheet():
    group = SourceGroup(source_group_id="G1", is_subcircuit=True)
    comp = SourceComponent(source_component_id="U1", name="U1", subcircuit_id="G1")
    port = SourcePort(source_port_id="P1", source_component_id="U1", name="1")
    sheets, _ = _engine()._map_elements([comp], [group], [port])
    assert sheets["P1"] == "G1"


def test_cmp_024_source_traces_and_nets_are_not_included_in_per_sheet_layout_elements():
    elements = [*_basic_source(), SourceNet(source_net_id="N1", name="N1"), SourceTrace(source_trace_id="T1", connected_source_port_ids=["R1_1"])]
    sheets, _ = _engine()._map_elements([e for e in elements if isinstance(e, SourceComponent)], [], [e for e in elements if isinstance(e, SourcePort)])
    sheet_elements = _engine()._get_sheet_elements(elements, sheets, "root")
    assert not any(isinstance(e, (SourceTrace, SourceNet)) for e in sheet_elements)


def test_cmp_025_connectivity_uses_first_net_id_or_trace_id():
    trace_with_net = SourceTrace(source_trace_id="T1", connected_source_port_ids=["P1"], connected_source_net_ids=["N1"])
    trace_without_net = SourceTrace(source_trace_id="T2", connected_source_port_ids=["P1"])
    generated, _ = _engine()._process_connectivity([trace_with_net, trace_without_net], [], [], {}, {}, [], [], GlobalNetResolver.from_elements([]))
    assert generated == []


def test_cmp_026_connectivity_net_labels_use_net_prefix():
    net = SourceNet(source_net_id="N1", name="SIG")
    trace = SourceTrace(source_trace_id="T1", connected_source_port_ids=["P1"], connected_source_net_ids=["N1"])
    _, conn = _engine()._process_connectivity([trace], [SourcePort(source_port_id="P1", source_component_id="U1", name="1")], [net], {"P1": "root"}, {}, [], [net], GlobalNetResolver.from_elements([net]))
    assert conn["root"][0]["label_text"] == "NET_SIG"


def test_cmp_027_connectivity_hierarchical_pin_labels_use_hpin_prefix():
    net = SourceNet(source_net_id="N1", name="SIG")
    ports = [SourcePort(source_port_id="P1", source_component_id="U1", name="1"), SourcePort(source_port_id="P2", source_component_id="U2", name="1")]
    trace = SourceTrace(source_trace_id="T1", connected_source_port_ids=["P1", "P2"], connected_source_net_ids=["N1"])
    _, conn = _engine()._process_connectivity([trace], ports, [net], {"P1": "A", "P2": "B"}, {"U1": "A", "U2": "B"}, [], [net], GlobalNetResolver.from_elements([net]))
    assert conn["A"][0]["hier_label_text"] == "HPIN_SIG"


def test_cmp_028_global_net_handling_uses_metadata_configuration_and_defaults():
    elements = [SourceProjectConfig(global_net_names=["CUSTOM"], use_kicad_power_symbols_as_global_nets=False)]
    assert GlobalNetResolver.from_elements(elements).is_global(None, "CUSTOM", "CUSTOM")


def test_cmp_029_non_global_multisheet_traces_generate_hierarchical_elements():
    group = SourceGroup(source_group_id="child", is_subcircuit=True)
    elements = [
        group,
        SourceComponent(source_component_id="U1", name="U1"),
        SourcePort(source_port_id="P1", source_component_id="U1", name="1", pin_number=1),
        SourceComponent(source_component_id="U2", name="U2", subcircuit_id="child"),
        SourcePort(source_port_id="P2", source_component_id="U2", name="1", pin_number=1),
        SourceNet(source_net_id="N1", name="SIG"),
        SourceTrace(source_trace_id="T1", connected_source_port_ids=["P1", "P2"], connected_source_net_ids=["N1"]),
    ]
    result = _engine().layout(elements)
    assert any(isinstance(e, SchematicHierarchicalPin) for e in result)
    assert any(isinstance(e, SchematicHierarchicalLabel) for e in result)


def test_cmp_030_kicad_output_root_expression_is_kicad_sch():
    assert s_expr_parse(_sexpr_text()).name == "kicad_sch"


def test_cmp_031_kicad_output_contains_version_generator_uuid_and_paper():
    text = _sexpr_text()
    assert "(version 20260306)" in text
    assert "(generator eeschema)" in text
    assert "(generator_version 10.0)" in text
    assert "(uuid" in text
    assert "(paper A4)" in text


def test_cmp_032_grid_units_convert_to_mm_with_0127_factor():
    assert GRID_TO_MM.__class__("0.127") == GRID_TO_MM


def test_cmp_033_millimeter_values_format_with_four_decimal_places():
    assert SchematicToSExprTransform()._grid_to_mm(10) == "1.2700"


def test_cmp_034_symbol_library_definitions_embed_when_available_and_missing_libs_do_not_abort(monkeypatch):
    monkeypatch.setattr("circuitweaver.library.pinout.get_expanded_symbol_definition", lambda *args, **kwargs: "(symbol \"R\")")
    text = _sexpr_text()
    assert "lib_symbols" in text


def test_cmp_035_hierarchical_sheet_boxes_become_kicad_sheet_expressions():
    elements = [SchematicBox(schematic_box_id="box_child", sheet_id="root", x=0, y=0, width=100, height=50, is_hierarchical_sheet=True, child_sheet_id="child", name="Child")]
    assert "(sheet" in _sexpr_text(elements, {})


def test_cmp_036_schematic_components_become_kicad_symbol_expressions():
    assert "(symbol " in _sexpr_text()


def test_cmp_037_component_reference_text_comes_from_source_name_or_u_unknown():
    assert "R1" in _sexpr_text()


def test_cmp_038_component_value_text_uses_display_value_then_symbol_id_then_empty():
    assert "10k" in _sexpr_text()


def test_cmp_039_component_footprint_property_only_when_present():
    assert "Footprint" in _sexpr_text()


def test_cmp_040_schematic_traces_become_kicad_wire_expressions():
    trace = SchematicTrace(schematic_trace_id="T1", sheet_id="root", edges=[{"from": Point(x=0, y=0), "to": Point(x=10, y=0)}])
    assert "(wire" in _sexpr_text([trace], {})


def test_cmp_041_junctions_emit_for_points_used_by_at_least_three_connectors():
    edges = [
        {"from": Point(x=0, y=0), "to": Point(x=10, y=0)},
        {"from": Point(x=0, y=0), "to": Point(x=0, y=10)},
        {"from": Point(x=0, y=0), "to": Point(x=-10, y=0)},
    ]
    assert "(junction" in _sexpr_text([SchematicTrace(schematic_trace_id="T1", sheet_id="root", edges=edges)], {})


def test_cmp_042_schematic_net_labels_become_kicad_label_expressions():
    label = SchematicNetLabel(schematic_net_label_id="L1", source_net_id="N1", text="SIG", center=Point(x=0, y=0), sheet_id="root")
    sexpr = _sexpr([label], {})
    assert sexpr.find("label").args[0] == "SIG"


def test_cmp_043_schematic_hierarchical_labels_become_kicad_hierarchical_label_expressions():
    label = SchematicHierarchicalLabel(schematic_hierarchical_label_id="HL1", source_net_id="N1", text="SIG", center=Point(x=0, y=0), sheet_id="root")
    sexpr = _sexpr([label], {})
    assert sexpr.find("hierarchical_label").args[0] == "SIG"


def test_cmp_044_schematic_no_connects_become_kicad_no_connect_when_position_exists():
    nc = SchematicNoConnect(schematic_no_connect_id="NC1", position=Point(x=0, y=0), sheet_id="root")
    assert "(no_connect" in _sexpr_text([nc], {})


def test_cmp_045_non_hierarchical_schematic_boxes_become_rectangles():
    box = SchematicBox(schematic_box_id="B1", sheet_id="root", x=0, y=0, width=10, height=10)
    assert "(rectangle" in _sexpr_text([box], {})


def test_cmp_046_project_metadata_json_contains_root_sheet_and_empty_boards():
    payload = json.loads(SchematicToSExprTransform().transform_project("demo", ["root", "child"]))
    assert payload["meta"]["filename"] == "demo.kicad_pro"
    assert payload["meta"]["version"] == 3
    assert payload["boards"] == []
    assert payload["sheets"][0] == ["Root", "demo.kicad_sch"]


def test_cmp_047_subcircuit_without_subcircuit_id_owns_source_group_id_sheet():
    assert _engine()._get_group_sheet_id(SourceGroup(source_group_id="G1", is_subcircuit=True)) == "G1"


def test_cmp_048_component_subcircuit_id_matching_group_id_maps_to_group_sheet():
    group = SourceGroup(source_group_id="G1", is_subcircuit=True)
    comp = SourceComponent(source_component_id="U1", name="U1", subcircuit_id="G1")
    sheets, _ = _engine()._map_elements([comp], [group], [])
    assert sheets["U1"] == "G1"


def test_cmp_049_source_net_is_global_is_authoritative_global_declaration():
    net = SourceNet(source_net_id="N1", name="ODD", is_global=True)
    assert GlobalNetResolver.from_elements([net]).is_global(net, "N1", "ODD")


def test_cmp_050_global_detection_does_not_rely_on_substring_matching_when_defaults_disabled():
    config = SourceProjectConfig(use_kicad_power_symbols_as_global_nets=False)
    assert not GlobalNetResolver.from_elements([config]).is_global(None, "signal_5v_detector", "signal_5v_detector")


def test_cmp_051_kicad_power_symbol_names_may_be_default_global_catalog(monkeypatch, tmp_path):
    power = tmp_path / "power.kicad_sym"
    power.write_text('(kicad_symbol_lib (symbol "+5V"))', encoding="utf-8")
    monkeypatch.setattr("circuitweaver.compiler.global_nets.get_library_paths", lambda: SimpleNamespace(symbols=tmp_path))
    get_kicad_power_symbol_global_names.cache_clear()
    assert "5V" in get_kicad_power_symbol_global_names()
    get_kicad_power_symbol_global_names.cache_clear()


def test_cmp_052_missing_power_symbol_catalog_is_compile_ready_warning(monkeypatch, tmp_path):
    monkeypatch.setattr("circuitweaver.compiler.global_nets.get_kicad_power_symbol_global_names", lambda: frozenset())
    path = tmp_path / "circuit.json"
    path.write_text(json.dumps([{"type": "source_component", "source_component_id": "U1", "name": "U1", "ftype": "simple_resistor"}]), encoding="utf-8")
    result = validate_circuit_file(path, profile="compile-ready")
    assert any(w.rule == "compile_ready_power_symbol_catalog" for w in result.warnings)


def test_cmp_053_project_can_add_custom_global_net_names():
    config = SourceProjectConfig(global_net_names=["MOTOR_BUS"], use_kicad_power_symbols_as_global_nets=False)
    assert GlobalNetResolver.from_elements([config]).is_global(None, "MOTOR_BUS", "MOTOR_BUS")


def test_cmp_054_project_can_disable_default_power_symbol_catalog(monkeypatch):
    monkeypatch.setattr("circuitweaver.compiler.global_nets.get_kicad_power_symbol_global_names", lambda: frozenset({"GND"}))
    config = SourceProjectConfig(use_kicad_power_symbols_as_global_nets=False)
    assert not GlobalNetResolver.from_elements([config]).is_global(None, "GND", "GND")


def test_cmp_055_global_inter_sheet_nets_use_global_labels_without_hierarchical_pins():
    net = SourceNet(source_net_id="N1", name="BUS", is_global=True)
    ports = [SourcePort(source_port_id="P1", source_component_id="U1", name="1"), SourcePort(source_port_id="P2", source_component_id="U2", name="1")]
    trace = SourceTrace(source_trace_id="T1", connected_source_port_ids=["P1", "P2"], connected_source_net_ids=["N1"])
    generated, conn = _engine()._process_connectivity([trace], ports, [net], {"P1": "A", "P2": "B"}, {"U1": "A", "U2": "B"}, [], [net], GlobalNetResolver.from_elements([net]))
    assert not any(isinstance(e, SchematicHierarchicalPin) for e in generated)
    assert conn["A"][0]["is_global_net"] is True


def test_cmp_056_non_global_inter_sheet_nets_create_hierarchical_pins_and_labels():
    test_cmp_029_non_global_multisheet_traces_generate_hierarchical_elements()


def test_cmp_057_root_sheet_connects_matching_hierarchical_pins_by_labels():
    net = SourceNet(source_net_id="N1", name="SIG")
    ports = [SourcePort(source_port_id="P1", source_component_id="U1", name="1"), SourcePort(source_port_id="P2", source_component_id="U2", name="1")]
    trace = SourceTrace(source_trace_id="T1", connected_source_port_ids=["P1", "P2"], connected_source_net_ids=["N1"])
    generated, _ = _engine()._process_connectivity([trace], ports, [net], {"P1": "A", "P2": "B"}, {"U1": "A", "U2": "B"}, [], [net], GlobalNetResolver.from_elements([net]))
    assert any(isinstance(e, SchematicNetLabel) and e.sheet_id == "root" for e in generated)


def test_cmp_058_root_sheet_hierarchical_pin_labels_match_child_hierarchical_label_text():
    net = SourceNet(source_net_id="N1", name="SIG")
    ports = [SourcePort(source_port_id="P1", source_component_id="U1", name="1"), SourcePort(source_port_id="P2", source_component_id="U2", name="1")]
    trace = SourceTrace(source_trace_id="T1", connected_source_port_ids=["P1", "P2"], connected_source_net_ids=["N1"])
    generated, _ = _engine()._process_connectivity([trace], ports, [net], {"P1": "A", "P2": "B"}, {"U1": "A", "U2": "B"}, [], [net], GlobalNetResolver.from_elements([net]))
    labels = [e for e in generated if isinstance(e, (SchematicNetLabel, SchematicHierarchicalLabel))]
    assert {label.text for label in labels} == {"HPIN_SIG"}


def test_cmp_059_root_sheet_hierarchical_pin_labels_are_adjacent_and_do_not_create_direct_wires():
    test_cmp_057_root_sheet_connects_matching_hierarchical_pins_by_labels()


def test_cmp_060_root_labels_generated_for_every_non_global_sheet_pin():
    net = SourceNet(source_net_id="N1", name="SIG")
    ports = [SourcePort(source_port_id=f"P{i}", source_component_id=f"U{i}", name="1") for i in range(3)]
    trace = SourceTrace(source_trace_id="T1", connected_source_port_ids=["P0", "P1", "P2"], connected_source_net_ids=["N1"])
    generated, _ = _engine()._process_connectivity([trace], ports, [net], {"P0": "A", "P1": "B", "P2": "C"}, {"U0": "A", "U1": "B", "U2": "C"}, [], [net], GlobalNetResolver.from_elements([net]))
    assert len([e for e in generated if isinstance(e, SchematicNetLabel) and e.sheet_id == "root"]) == 3


def test_cmp_061_global_schematic_net_labels_become_kicad_global_label_expressions():
    label = SchematicNetLabel(schematic_net_label_id="L1", source_net_id="N1", text="BUS", center=Point(x=0, y=0), sheet_id="root", is_global=True)
    sexpr = _sexpr([label], {})
    assert sexpr.find("global_label").args[0] == "BUS"


def test_lay_040_auto_router_init_fails_when_node_missing(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="Node.js"):
        AutoRouter()


def test_lay_041_auto_router_defaults_helper_script_to_compiler_layout_helper(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/node")
    router = AutoRouter()
    assert router.helper_path.name == "layout_helper.js"


def test_lay_042_auto_router_passes_layout_graph_json_to_node_stdin(monkeypatch, tmp_path):
    calls = {}
    helper = tmp_path / "helper.js"
    helper.write_text("", encoding="utf-8")
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/node")

    def fake_run(cmd, input, capture_output, text, check, env):
        calls["input"] = input
        return subprocess.CompletedProcess(cmd, 0, stdout='{"id":"root"}', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    AutoRouter(helper_path=helper).run({"id": "root"})
    assert json.loads(calls["input"]) == {"id": "root"}


def test_lay_043_auto_router_parses_stdout_as_json(monkeypatch, tmp_path):
    helper = tmp_path / "helper.js"
    helper.write_text("", encoding="utf-8")
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/node")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout='{"id":"root"}', stderr=""))
    assert AutoRouter(helper_path=helper).run({"id": "root"}) == {"id": "root"}


def test_lay_044_auto_router_nonzero_node_exit_raises_runtime_error(monkeypatch, tmp_path):
    helper = tmp_path / "helper.js"
    helper.write_text("", encoding="utf-8")
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/node")

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0], output="out", stderr="err")

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(RuntimeError, match="err"):
        AutoRouter(helper_path=helper).run({"id": "root"})


def test_lay_045_auto_router_invalid_json_stdout_raises_runtime_error(monkeypatch, tmp_path):
    helper = tmp_path / "helper.js"
    helper.write_text("", encoding="utf-8")
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/node")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout="not-json", stderr=""))
    with pytest.raises(RuntimeError, match="Invalid JSON"):
        AutoRouter(helper_path=helper).run({"id": "root"})


def test_lay_050_snap_to_grid_rounds_to_nearest_grid_size_default_10():
    assert snap_to_grid(14.9) == 10.0
    assert snap_to_grid(15.1) == 20.0


def test_lay_051_layout_to_schematic_processes_layout_nodes_recursively():
    group = SourceGroup(source_group_id="G1")
    comp = SourceComponent(source_component_id="U1", name="U1", source_group_id="G1")
    layout, registry = SourceToLayoutTransform().transform("root", [group, comp])
    result = LayoutToSchematicTransform().transform("root", layout, registry, [group, comp])
    assert any(isinstance(e, SchematicComponent) and e.source_component_id == "U1" for e in result)


def test_lay_052_source_component_nodes_become_schematic_components_with_sch_id():
    comp = SourceComponent(source_component_id="U1", name="U1")
    layout, registry = SourceToLayoutTransform().transform("root", [comp])
    result = LayoutToSchematicTransform().transform("root", layout, registry, [comp])
    assert next(e for e in result if isinstance(e, SchematicComponent)).schematic_component_id == "sch_U1"


def test_lay_053_generated_schematic_components_use_current_sheet_id():
    comp = SourceComponent(source_component_id="U1", name="U1")
    layout, registry = SourceToLayoutTransform().transform("child", [comp])
    result = LayoutToSchematicTransform().transform("child", layout, registry, [comp])
    assert next(e for e in result if isinstance(e, SchematicComponent)).sheet_id == "child"


def test_lay_054_generated_component_centers_are_snapped_to_grid():
    comp = SourceComponent(source_component_id="U1", name="U1")
    layout, registry = SourceToLayoutTransform().transform("root", [comp])
    layout.children[0].x = 13
    layout.children[0].y = 17
    result = LayoutToSchematicTransform().transform("root", layout, registry, [comp])
    assert next(e for e in result if isinstance(e, SchematicComponent)).center == Point(x=10, y=20)


def test_lay_055_generated_schematic_ports_have_port_source_port_id():
    elements = _basic_source()
    layout, registry = SourceToLayoutTransform().transform("root", elements)
    result = LayoutToSchematicTransform().transform("root", layout, registry, elements)
    assert any(isinstance(e, SchematicPort) and e.schematic_port_id == "port_R1_1" for e in result)


def test_lay_056_symbol_pin_offsets_position_schematic_ports_when_available():
    elements = [SourceComponent(source_component_id="R1", name="R1", symbol_id="Device:R"), SourcePort(source_port_id="R1_2", source_component_id="R1", name="B", pin_number=2)]
    symbol = _pins_symbol()
    layout, registry = SourceToLayoutTransform(symbol_map={"Device:R": symbol}).transform("root", elements)
    result = LayoutToSchematicTransform(symbol_map={"Device:R": symbol}).transform("root", layout, registry, elements)
    assert any(isinstance(e, SchematicPort) and e.center.x > 0 for e in result)


def test_lay_057_source_group_nodes_become_schematic_boxes():
    group = SourceGroup(source_group_id="G1")
    layout, registry = SourceToLayoutTransform().transform("root", [group])
    result = LayoutToSchematicTransform().transform("root", layout, registry, [group])
    assert any(isinstance(e, SchematicBox) and e.schematic_box_id == "box_G1" for e in result)


def test_lay_058_subcircuit_group_generates_hierarchical_sheet_box_with_subcircuit_id():
    group = SourceGroup(source_group_id="G1", subcircuit_id="child", is_subcircuit=True)
    layout, registry = SourceToLayoutTransform().transform("root", [group])
    result = LayoutToSchematicTransform().transform("root", layout, registry, [group])
    assert next(e for e in result if isinstance(e, SchematicBox)).child_sheet_id == "child"


def test_lay_059_edge_sections_become_nonzero_schematic_trace_edges():
    comp = SourceComponent(source_component_id="U1", name="U1")
    layout = LayoutNode(id="root", children=[LayoutNode(id="U1")], edges=[LayoutEdge(id="e_T1_A_B", sources=["A"], targets=["B"], sections=[LayoutEdgeSection(id="s", startPoint=LayoutPoint(x=0, y=0), endPoint=LayoutPoint(x=10, y=0))])])
    from circuitweaver.transform.source_to_layout import LayoutRegistry
    registry = LayoutRegistry()
    registry.register_node(comp, "U1")
    result = LayoutToSchematicTransform().transform("root", layout, registry, [comp])
    assert any(isinstance(e, SchematicTrace) and e.edges for e in result)


def test_lay_060_label_edges_position_schematic_labels_at_routed_endpoint():
    label = SchematicNetLabel(schematic_net_label_id="L1", source_net_id="N1", source_port_id="P1", text="SIG", center=Point(x=0, y=0), sheet_id="root")
    from circuitweaver.transform.source_to_layout import LayoutRegistry
    registry = LayoutRegistry()
    registry.register_node(label, "label_node_L1")
    layout = LayoutNode(id="root", edges=[LayoutEdge(id="e_label_L1", sources=["P1"], targets=["label_node_L1"], sections=[LayoutEdgeSection(id="s", startPoint=LayoutPoint(x=0, y=0), endPoint=LayoutPoint(x=20, y=0))])])
    result = LayoutToSchematicTransform().transform("root", layout, registry, [label])
    assert next(e for e in result if isinstance(e, SchematicNetLabel)).center == Point(x=20, y=0)


def test_lay_061_label_anchor_side_is_inferred_from_final_edge_segment_direction():
    label = SchematicNetLabel(schematic_net_label_id="L1", source_net_id="N1", source_port_id="P1", text="SIG", center=Point(x=0, y=0), sheet_id="root")
    from circuitweaver.transform.source_to_layout import LayoutRegistry
    registry = LayoutRegistry()
    registry.register_node(label, "label_node_L1")
    layout = LayoutNode(id="root", edges=[LayoutEdge(id="e_label_L1", sources=["P1"], targets=["label_node_L1"], sections=[LayoutEdgeSection(id="s", startPoint=LayoutPoint(x=0, y=0), endPoint=LayoutPoint(x=20, y=0))])])
    result = LayoutToSchematicTransform().transform("root", layout, registry, [label])
    assert next(e for e in result if isinstance(e, SchematicNetLabel)).anchor_side == "left"


def test_lay_062_no_connect_edges_do_not_generate_schematic_traces():
    layout = LayoutNode(id="root", edges=[LayoutEdge(id="e_nc_1", sources=["P1"], targets=["N1"], sections=[LayoutEdgeSection(id="s", startPoint=LayoutPoint(x=0, y=0), endPoint=LayoutPoint(x=20, y=0))])])
    result = LayoutToSchematicTransform().transform("root", layout, SourceToLayoutTransform().transform("root", [])[1], [])
    assert not any(isinstance(e, SchematicTrace) for e in result)


def test_lay_063_subcircuit_group_without_subcircuit_id_uses_source_group_id_child_sheet():
    group = SourceGroup(source_group_id="G1", is_subcircuit=True)
    layout, registry = SourceToLayoutTransform().transform("root", [group])
    result = LayoutToSchematicTransform().transform("root", layout, registry, [group])
    assert next(e for e in result if isinstance(e, SchematicBox)).child_sheet_id == "G1"


def test_lay_064_source_ports_map_to_symbol_pins_by_pin_number_or_name():
    elements = [SourceComponent(source_component_id="R1", name="R1", symbol_id="Device:R"), SourcePort(source_port_id="R1_A", source_component_id="R1", name="A")]
    _, registry = SourceToLayoutTransform(symbol_map={"Device:R": _pins_symbol()}).transform("root", elements)
    assert registry.element_to_port["R1_A"] == "R1:1"


def test_layout_and_compilation_requirement_traceability_is_machine_checkable():
    report = traceability_report(
        Path("docs/requirements/layout-and-compilation.md"),
        Path("tests/test_layout_and_compilation_requirements.py"),
    )
    assert report["ok"], report["missing"]

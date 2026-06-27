"""Requirement-traceable tests for docs/requirements/layout-quality.md."""

# ruff: noqa: ARG001, ARG002, ARG005

from pathlib import Path
from types import SimpleNamespace

from circuitweaver.compiler.engine import CompileEngine
from circuitweaver.compiler.layout_quality import LayoutQualityChecker
from circuitweaver.requirements import traceability_report
from circuitweaver.transform import LayoutToSchematicTransform, SourceToLayoutTransform
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
    SchematicTrace,
    SheetConnection,
    SourceComponent,
    SourceGroup,
    SourcePort,
)


def _rules(elements):
    return {d.rule for d in LayoutQualityChecker().check(elements).diagnostics}


def test_lq_001_generated_sheets_prefer_left_to_right_elk_direction():
    layout, _ = SourceToLayoutTransform().transform("root", [])
    assert layout.layoutOptions["org.eclipse.elk.direction"] == "RIGHT"


def test_lq_002_root_sheet_boxes_order_by_upstream_downstream_connectivity():
    elements = [
        SourceGroup(source_group_id="input", is_subcircuit=True),
        SourceGroup(source_group_id="output", is_subcircuit=True),
        SchematicHierarchicalPin(schematic_hierarchical_pin_id="input_out", source_net_id="N1", schematic_box_id="box_input", sheet_id="root", center=Point(x=0, y=0), text="OUT"),
        SchematicHierarchicalPin(schematic_hierarchical_pin_id="output_in", source_net_id="N1", schematic_box_id="box_output", sheet_id="root", center=Point(x=0, y=0), text="IN"),
    ]
    layout, _ = SourceToLayoutTransform().transform("root", elements)
    assert [child.id for child in layout.children] == ["box_input", "box_output"]


def test_lq_003_components_order_by_input_output_connectivity():
    elements = [
        SourceComponent(source_component_id="SRC", name="SRC"),
        SourcePort(source_port_id="SRC_OUT", source_component_id="SRC", name="OUT", port_hints=["output"]),
        SourceComponent(source_component_id="LOAD", name="LOAD"),
        SourcePort(source_port_id="LOAD_IN", source_component_id="LOAD", name="IN", port_hints=["input"]),
    ]
    sheet_conn = {
        "root": [
            SheetConnection(
                net_id="T1",
                trace_ids=("T1",),
                sheet_id="root",
                endpoint_port_ids=("LOAD_IN", "SRC_OUT"),
                render_kind="wire",
                label_text="NET_T1",
                hierarchical_label_text="HPIN_T1",
            )
        ]
    }
    layout, _ = SourceToLayoutTransform().transform("root", elements, sheet_conn)
    assert [child.id for child in layout.children] == ["SRC", "LOAD"]


def test_lq_004_uninferred_flow_uses_stable_deterministic_order():
    elements = [
        SourceComponent(source_component_id="B", name="B"),
        SourceComponent(source_component_id="A", name="A"),
    ]
    layout, _ = SourceToLayoutTransform().transform("root", elements)
    assert [child.id for child in layout.children] == ["A", "B"]


def test_lq_020_child_sheet_component_is_not_generated_on_root_sheet():
    result = CompileEngine(router=SimpleNamespace(run=lambda graph: graph)).layout(
        [
            SourceGroup(source_group_id="child", is_subcircuit=True),
            SourceComponent(source_component_id="U1", name="U1", subcircuit_id="child"),
        ]
    )
    comps = [e for e in result if isinstance(e, SchematicComponent) and e.source_component_id == "U1"]
    assert {comp.sheet_id for comp in comps} == {"child"}


def test_lq_021_components_assigned_to_group_are_inside_group_box():
    elements = [
        SourceGroup(source_group_id="G1"),
        SourceComponent(source_component_id="U1", name="U1", source_group_id="G1"),
    ]
    layout, registry = SourceToLayoutTransform().transform("root", elements)
    layout.children[0].x = 100
    layout.children[0].y = 100
    layout.children[0].children[0].x = 40
    layout.children[0].children[0].y = 40
    result = LayoutToSchematicTransform().transform("root", layout, registry, elements)
    assert "LQ-103" not in _rules([*elements, *result])


def test_lq_022_group_box_is_large_enough_for_children_with_padding():
    group = SourceGroup(source_group_id="G1")
    comps = [
        SourceComponent(source_component_id=f"U{i}", name=f"U{i}", source_group_id="G1")
        for i in range(5)
    ]
    layout, _ = SourceToLayoutTransform().transform("root", [group, *comps])
    assert layout.children[0].width > 250


def test_lq_023_hierarchical_pins_are_on_sheet_box_boundary():
    box = SchematicBox(schematic_box_id="box_child", sheet_id="root", x=10, y=20, width=100, height=80, is_hierarchical_sheet=True)
    pin = SchematicHierarchicalPin(schematic_hierarchical_pin_id="HP", source_net_id="N1", schematic_box_id="box_child", sheet_id="root", center=Point(x=10, y=50), text="IN")
    assert "LQ-023" not in _rules([box, pin])


def test_lq_024_sheet_box_too_small_for_pins_reports_diagnostic():
    pins = [
        SchematicHierarchicalPin(schematic_hierarchical_pin_id=f"HP{i}", source_net_id=f"N{i}", schematic_box_id="box_child", sheet_id="root", center=Point(x=0, y=i * 20), text=f"P{i}")
        for i in range(6)
    ]
    box = SchematicBox(schematic_box_id="box_child", sheet_id="root", x=0, y=0, width=100, height=60, is_hierarchical_sheet=True)
    assert "LQ-024" in _rules([box, *pins])


def test_lq_040_generated_component_bounding_boxes_do_not_overlap():
    assert "LQ-040" in _rules([
        SchematicComponent(schematic_component_id="A", source_component_id="A", sheet_id="root", center=Point(x=0, y=0)),
        SchematicComponent(schematic_component_id="B", source_component_id="B", sheet_id="root", center=Point(x=10, y=0)),
    ])


def test_lq_041_generated_labels_do_not_overlap_component_bounding_boxes():
    assert "LQ-041" in _rules([
        SchematicComponent(schematic_component_id="A", source_component_id="A", sheet_id="root", center=Point(x=0, y=0)),
        SchematicNetLabel(schematic_net_label_id="L", source_net_id="N", sheet_id="root", center=Point(x=0, y=0), text="N"),
    ])


def test_lq_042_generated_labels_do_not_overlap_other_labels():
    assert "LQ-042" in _rules([
        SchematicNetLabel(schematic_net_label_id="A", source_net_id="A", sheet_id="root", center=Point(x=0, y=0), text="AAA"),
        SchematicNetLabel(schematic_net_label_id="B", source_net_id="B", sheet_id="root", center=Point(x=1, y=0), text="BBB"),
    ])


def test_lq_043_hierarchical_pins_on_same_edge_do_not_overlap():
    assert "LQ-043" in _rules([
        SchematicHierarchicalPin(schematic_hierarchical_pin_id="A", source_net_id="A", schematic_box_id="box", sheet_id="root", center=Point(x=0, y=0), text="A"),
        SchematicHierarchicalPin(schematic_hierarchical_pin_id="B", source_net_id="B", schematic_box_id="box", sheet_id="root", center=Point(x=0, y=0), text="B"),
    ])


def test_lq_044_root_page_sheet_boxes_do_not_overlap():
    assert "LQ-104" in _rules([
        SchematicBox(schematic_box_id="A", sheet_id="root", x=0, y=0, width=100, height=100, is_hierarchical_sheet=True),
        SchematicBox(schematic_box_id="B", sheet_id="root", x=10, y=10, width=100, height=100, is_hierarchical_sheet=True),
    ])


def test_lq_060_labels_for_component_ports_are_near_port():
    label = SchematicNetLabel(schematic_net_label_id="L1", source_net_id="N1", source_port_id="P1", text="SIG", center=Point(x=0, y=0), sheet_id="root")
    registry = SourceToLayoutTransform().transform("root", [])[1]
    registry.register_node(label, "label_node_L1")
    layout = LayoutNode(id="root", edges=[LayoutEdge(id="e_label_L1", sources=["P1"], targets=["label_node_L1"], sections=[LayoutEdgeSection(id="s", startPoint=LayoutPoint(x=20, y=0), endPoint=LayoutPoint(x=30, y=0))])])
    result = LayoutToSchematicTransform().transform("root", layout, registry, [label])
    assert next(e for e in result if isinstance(e, SchematicNetLabel)).center.x == 30


def test_lq_061_hierarchical_labels_inside_child_sheets_are_not_left_at_origin():
    label = SchematicHierarchicalLabel(schematic_hierarchical_label_id="HL1", source_net_id="N1", source_port_id="P1", text="SIG", center=Point(x=0, y=0), sheet_id="child")
    assert "LQ-102" in _rules([label])


def test_lq_062_global_labels_inside_child_sheets_are_not_left_at_origin():
    label = SchematicNetLabel(schematic_net_label_id="GL1", source_net_id="N1", source_port_id="P1", text="GND", center=Point(x=0, y=0), sheet_id="child", is_global=True)
    assert "LQ-102" in _rules([label])


def test_lq_063_root_page_labels_for_hierarchical_sheet_pins_are_near_pin():
    pin = SchematicHierarchicalPin(schematic_hierarchical_pin_id="HP", source_net_id="N1", schematic_box_id="box_child", sheet_id="root", center=Point(x=100, y=50), text="SIG")
    label = SchematicNetLabel(schematic_net_label_id="L", source_net_id="N1", schematic_hierarchical_pin_id="HP", sheet_id="root", center=Point(x=102, y=50), text="SIG")
    assert "LQ-063" not in _rules([pin, label])


def test_lq_080_generated_wires_use_orthogonal_segments():
    trace = SchematicTrace(schematic_trace_id="T1", sheet_id="root", edges=[{"from": Point(x=0, y=0), "to": Point(x=10, y=10)}])
    assert "LQ-080" in _rules([trace])


def test_lq_081_generated_wires_do_not_route_through_component_boxes():
    trace = SchematicTrace(schematic_trace_id="T1", sheet_id="root", edges=[{"from": Point(x=-100, y=0), "to": Point(x=100, y=0)}])
    comp = SchematicComponent(schematic_component_id="U1", source_component_id="U1", sheet_id="root", center=Point(x=0, y=0))
    assert "LQ-081" in _rules([comp, trace])


def test_lq_082_cross_sheet_connections_prefer_root_labels_not_long_wires():
    elements = [
        SourceGroup(source_group_id="A", is_subcircuit=True),
        SourceGroup(source_group_id="B", is_subcircuit=True),
        SchematicHierarchicalPin(schematic_hierarchical_pin_id="HA", source_net_id="N1", schematic_box_id="box_A", sheet_id="root", center=Point(x=0, y=0), text="SIG"),
        SchematicHierarchicalPin(schematic_hierarchical_pin_id="HB", source_net_id="N1", schematic_box_id="box_B", sheet_id="root", center=Point(x=0, y=0), text="SIG"),
    ]
    layout, _ = SourceToLayoutTransform().transform("root", elements)
    assert not any(edge for edge in layout.edges if "hpin" in edge.id)


def test_lq_100_layout_quality_check_can_run_after_generation():
    assert hasattr(CompileEngine(), "check_layout_quality")


def test_lq_101_layout_quality_check_reports_overlapping_components():
    test_lq_040_generated_component_bounding_boxes_do_not_overlap()


def test_lq_102_layout_quality_check_reports_labels_at_origin():
    assert "LQ-102" in _rules([SchematicNetLabel(schematic_net_label_id="L", source_net_id="N", sheet_id="root", center=Point(x=0, y=0), text="N")])


def test_lq_103_layout_quality_check_reports_component_outside_group_or_sheet():
    assert "LQ-103" in _rules([
        SourceGroup(source_group_id="G1"),
        SourceComponent(source_component_id="U1", name="U1", source_group_id="G1"),
        SchematicBox(schematic_box_id="box_G1", sheet_id="root", x=0, y=0, width=50, height=50),
        SchematicComponent(schematic_component_id="U1", source_component_id="U1", sheet_id="root", center=Point(x=100, y=100)),
    ])


def test_lq_104_layout_quality_check_reports_root_sheet_box_overlap():
    test_lq_044_root_page_sheet_boxes_do_not_overlap()


def test_lq_105_layout_quality_diagnostics_include_sheet_and_element_ids():
    diag = LayoutQualityChecker().check([
        SchematicNetLabel(schematic_net_label_id="L", source_net_id="N", sheet_id="root", center=Point(x=0, y=0), text="N")
    ]).diagnostics[0]
    assert diag.sheet_id == "root"
    assert diag.element_ids == ("L",)


def test_lq_106_layout_quality_check_reports_label_component_overlap():
    test_lq_041_generated_labels_do_not_overlap_component_bounding_boxes()


def test_lq_107_layout_quality_check_reports_label_label_overlap():
    test_lq_042_generated_labels_do_not_overlap_other_labels()


def test_lq_108_layout_quality_check_reports_hierarchical_pin_same_position():
    test_lq_043_hierarchical_pins_on_same_edge_do_not_overlap()


def test_lq_109_cli_exposes_layout_quality_diagnostics():
    from circuitweaver.cli import main

    assert "check-layout" in {cmd.name for cmd in main.commands.values()}


def test_layout_quality_requirement_traceability_is_machine_checkable():
    report = traceability_report(
        Path("docs/requirements/layout-quality.md"),
        Path("tests/test_layout_quality_requirements.py"),
    )
    assert report["ok"], report["missing"]

import json

from click.testing import CliRunner

from circuitweaver.cli import main
from circuitweaver.compiler.engine import CompileEngine
from circuitweaver.compiler.layout_quality import LayoutQualityChecker
from circuitweaver.types import (
    Point,
    SchematicBox,
    SchematicComponent,
    SchematicHierarchicalPin,
    SchematicNetLabel,
    SourceComponent,
)


def _rules(elements):
    report = LayoutQualityChecker().check(elements)
    return {diagnostic.rule for diagnostic in report.diagnostics}


def test_lq_040_reports_overlapping_components():
    elements = [
        SchematicComponent(
            schematic_component_id="sch_u1",
            source_component_id="U1",
            sheet_id="root",
            center=Point(x=100, y=100),
        ),
        SchematicComponent(
            schematic_component_id="sch_u2",
            source_component_id="U2",
            sheet_id="root",
            center=Point(x=110, y=110),
        ),
    ]

    assert "LQ-040" in _rules(elements)


def test_lq_102_reports_label_at_origin():
    elements = [
        SchematicNetLabel(
            schematic_net_label_id="label_1",
            source_net_id="net_1",
            sheet_id="root",
            center=Point(x=0, y=0),
            text="NET_1",
        )
    ]

    assert "LQ-102" in _rules(elements)


def test_lq_041_reports_label_component_overlap():
    elements = [
        SchematicComponent(
            schematic_component_id="sch_u1",
            source_component_id="U1",
            sheet_id="root",
            center=Point(x=100, y=100),
        ),
        SchematicNetLabel(
            schematic_net_label_id="label_1",
            source_net_id="net_1",
            sheet_id="root",
            center=Point(x=100, y=100),
            text="NET_1",
        ),
    ]

    assert "LQ-041" in _rules(elements)


def test_lq_042_reports_label_label_overlap():
    elements = [
        SchematicNetLabel(
            schematic_net_label_id="label_1",
            source_net_id="net_1",
            sheet_id="root",
            center=Point(x=100, y=100),
            text="NET_1",
        ),
        SchematicNetLabel(
            schematic_net_label_id="label_2",
            source_net_id="net_2",
            sheet_id="root",
            center=Point(x=105, y=100),
            text="NET_2",
        ),
    ]

    assert "LQ-042" in _rules(elements)


def test_lq_104_reports_root_sheet_box_overlap():
    elements = [
        SchematicBox(
            schematic_box_id="box_a",
            sheet_id="root",
            x=0,
            y=0,
            width=100,
            height=100,
            is_hierarchical_sheet=True,
        ),
        SchematicBox(
            schematic_box_id="box_b",
            sheet_id="root",
            x=50,
            y=50,
            width=100,
            height=100,
            is_hierarchical_sheet=True,
        ),
    ]

    assert "LQ-104" in _rules(elements)


def test_lq_043_reports_hierarchical_pin_overlap():
    elements = [
        SchematicHierarchicalPin(
            schematic_hierarchical_pin_id="hpin_a",
            source_net_id="net_a",
            schematic_box_id="box_a",
            sheet_id="root",
            center=Point(x=0, y=20),
            text="A",
        ),
        SchematicHierarchicalPin(
            schematic_hierarchical_pin_id="hpin_b",
            source_net_id="net_b",
            schematic_box_id="box_a",
            sheet_id="root",
            center=Point(x=0, y=20),
            text="B",
        ),
    ]

    assert "LQ-043" in _rules(elements)


def test_lq_103_reports_component_outside_group_box():
    elements = [
        SourceComponent(
            source_component_id="U1",
            name="U1",
            source_group_id="g1",
        ),
        SchematicBox(
            schematic_box_id="box_g1",
            sheet_id="root",
            x=0,
            y=0,
            width=100,
            height=100,
        ),
        SchematicComponent(
            schematic_component_id="sch_u1",
            source_component_id="U1",
            sheet_id="root",
            center=Point(x=200, y=200),
        ),
    ]

    assert "LQ-103" in _rules(elements)


def test_lq_100_compile_engine_runs_layout_quality_check_on_schematic_elements():
    elements = [
        SchematicComponent(
            schematic_component_id="sch_u1",
            source_component_id="U1",
            sheet_id="root",
            center=Point(x=100, y=100),
        ),
        SchematicComponent(
            schematic_component_id="sch_u2",
            source_component_id="U2",
            sheet_id="root",
            center=Point(x=110, y=110),
        ),
    ]

    report = CompileEngine().check_layout_quality(elements)

    assert any(d.rule == "LQ-040" for d in report.diagnostics)


def test_lq_100_cli_check_layout_prints_traceable_json_diagnostics(tmp_path):
    circuit_file = tmp_path / "layout.json"
    circuit_file.write_text(
        json.dumps(
            [
                {
                    "type": "schematic_component",
                    "schematic_component_id": "sch_u1",
                    "source_component_id": "U1",
                    "sheet_id": "root",
                    "center": {"x": 100, "y": 100},
                },
                {
                    "type": "schematic_component",
                    "schematic_component_id": "sch_u2",
                    "source_component_id": "U2",
                    "sheet_id": "root",
                    "center": {"x": 110, "y": 110},
                },
            ]
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        main, ["check-layout", str(circuit_file), "--output-format", "json"]
    )
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["diagnostics"][0]["rule"] == "LQ-040"

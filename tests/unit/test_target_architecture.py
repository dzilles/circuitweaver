"""Requirement-traceable tests for target architecture primitives."""

import json

from circuitweaver.compiler.engine import CompileEngine
from circuitweaver.project import CircuitProject
from circuitweaver.results import OutputArtifact, StageResult
from circuitweaver.types import Point, SchematicComponent, SourceComponent, SourcePort


def test_arch_020_circuit_project_is_first_class_container():
    project = CircuitProject(
        elements=[
            SourceComponent(source_component_id="U1", name="U1"),
            SourcePort(
                source_port_id="U1_1",
                source_component_id="U1",
                pin_number="1",
                name="1",
            ),
        ],
        name="demo",
    )

    assert project.name == "demo"
    assert project.source_components["U1"].name == "U1"
    assert project.source_ports["U1_1"].pin_number == 1


def test_arch_021_circuit_project_separates_source_and_schematic_elements():
    project = CircuitProject(
        elements=[
            SourceComponent(source_component_id="U1", name="U1"),
            SchematicComponent(
                schematic_component_id="sch_u1",
                source_component_id="U1",
                sheet_id="root",
                center=Point(x=10, y=20),
            ),
        ]
    )

    assert [e.type for e in project.source_elements] == ["source_component"]
    assert [e.type for e in project.schematic_elements] == ["schematic_component"]


def test_arch_001_compiler_exposes_parse_validate_layout_schematic_kicad_and_write_stages(
    tmp_path,
):
    engine = CompileEngine()
    circuit_file = tmp_path / "demo.json"
    circuit_file.write_text(
        json.dumps(
            [
                {
                    "type": "source_component",
                    "source_component_id": "U1",
                    "name": "U1",
                }
            ]
        ),
        encoding="utf-8",
    )

    parse_result = engine.parse_file(circuit_file)
    assert parse_result.ok
    assert parse_result.stage == "parse"

    validate_result = engine.validate_project(parse_result.value)
    assert validate_result.ok
    assert validate_result.stage == "validate"

    layout_result = engine.layout_project(validate_result.value)
    assert layout_result.ok
    assert layout_result.stage == "layout"

    schematic_result = engine.schematic_project(layout_result.value)
    assert schematic_result.ok
    assert schematic_result.stage == "schematic"

    kicad_result = engine.kicad_project(schematic_result.value)
    assert kicad_result.ok
    assert kicad_result.stage == "kicad_transform"

    write_result = engine.write_kicad(kicad_result.value, tmp_path / "out")
    assert write_result.ok
    assert write_result.stage == "write"


def test_arch_002_kicad_transform_can_run_in_memory_without_writing_files(tmp_path):
    engine = CompileEngine()
    project = CircuitProject(
        name="memory_only",
        elements=[
            SchematicComponent(
                schematic_component_id="sch_u1",
                source_component_id="U1",
                sheet_id="root",
                center=Point(x=10, y=20),
            )
        ],
    )

    result = engine.kicad_project(project)

    assert result.ok
    assert "root" in result.value.schematics
    assert result.value.project_file_content
    assert not (tmp_path / "memory_only.kicad_sch").exists()


def test_arch_003_write_stage_is_the_only_stage_that_creates_kicad_files(tmp_path):
    engine = CompileEngine()
    project = CircuitProject(
        name="written",
        elements=[
            SchematicComponent(
                schematic_component_id="sch_u1",
                source_component_id="U1",
                sheet_id="root",
                center=Point(x=10, y=20),
            )
        ],
    )
    kicad_result = engine.kicad_project(project)

    write_result = engine.write_kicad(kicad_result.value, tmp_path)

    assert write_result.ok
    assert (tmp_path / "written.kicad_sch").exists()
    assert (tmp_path / "written.kicad_pro").exists()
    assert {artifact.kind for artifact in write_result.artifacts} == {
        "kicad_schematic",
        "kicad_project",
    }


def test_arch_005_stage_result_reports_structured_errors():
    result = StageResult(stage="example")
    result.add_error("bad_input", "Input could not be used", element_id="U1")

    payload = result.to_dict()

    assert result.ok is False
    assert payload["errors"][0]["code"] == "bad_input"
    assert payload["errors"][0]["element_id"] == "U1"


def test_arch_006_pipeline_exposes_intermediate_artifact_metadata():
    result = StageResult(
        stage="example",
        artifacts=[OutputArtifact(kind="in_memory", name="demo")],
    )

    assert result.to_dict()["artifacts"][0]["kind"] == "in_memory"

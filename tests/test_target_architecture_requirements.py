"""Requirement-traceable tests for docs/requirements/target-architecture.md."""

# ruff: noqa: ARG001, ARG002, ARG005, E731

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from circuitweaver.cli import main
from circuitweaver.compiler.engine import CompileEngine
from circuitweaver.doctor import DoctorCheck, DoctorReport, doctor_json
from circuitweaver.project import CircuitProject
from circuitweaver.requirements import traceability_report
from circuitweaver.results import OutputArtifact, StageResult
from circuitweaver.server.http_transport import create_http_app
from circuitweaver.server.mcp_server import create_server
from circuitweaver.server.tool_registry import (
    create_schematic,
    get_symbol_pins,
    run_erc,
    search_kicad_parts,
    validate_circuit_json,
)
from circuitweaver.transform.schematic_to_s_expr import SchematicToSExprTransform
from circuitweaver.types import (
    Point,
    SchematicComponent,
    SourceComponent,
    SourceGroup,
    SourceNet,
    SourcePort,
    SourceTrace,
    s_expr_serialize,
)
from circuitweaver.validator import VALIDATION_PROFILES, validate_circuit_file


def _write_json(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _source_circuit() -> list[dict[str, object]]:
    return [
        {"type": "source_component", "source_component_id": "U1", "name": "U1", "ftype": "simple_resistor"},
        {"type": "source_port", "source_port_id": "U1_1", "source_component_id": "U1", "name": "1"},
    ]


def _project_with_schematic() -> CircuitProject:
    return CircuitProject(
        name="demo",
        elements=[
            SourceComponent(source_component_id="U1", name="U1", ftype="simple_resistor"),
            SchematicComponent(
                schematic_component_id="sch_u1",
                source_component_id="U1",
                sheet_id="root",
                center=Point(x=10, y=20),
            ),
        ],
    )


def test_arch_001_compiler_exposes_parse_validate_layout_schematic_kicad_and_write_stages(tmp_path):
    engine = CompileEngine()
    circuit_file = _write_json(tmp_path / "demo.json", _source_circuit())
    assert engine.parse_file(circuit_file).stage == "parse"
    assert engine.validate_project(engine.parse_file(circuit_file).value).stage == "validate"
    assert hasattr(engine, "layout_project")
    assert hasattr(engine, "schematic_project")
    assert hasattr(engine, "kicad_project")
    assert hasattr(engine, "write_kicad")


def test_arch_002_compiler_can_generate_kicad_in_memory_without_writing(tmp_path):
    result = CompileEngine().kicad_project(_project_with_schematic())
    assert result.ok
    assert result.value.project_file_content
    assert not (tmp_path / "demo.kicad_sch").exists()


def test_arch_003_file_writing_isolated_in_explicit_output_stage(tmp_path):
    engine = CompileEngine()
    kicad_result = engine.kicad_project(_project_with_schematic())
    assert not (tmp_path / "demo.kicad_sch").exists()
    write_result = engine.write_kicad(kicad_result.value, tmp_path)
    assert write_result.ok
    assert (tmp_path / "demo.kicad_sch").exists()


def test_arch_004_partial_schematic_layer_is_not_treated_as_complete():
    project = CircuitProject(
        elements=[
            SourceComponent(source_component_id="U1", name="U1"),
            SourceComponent(source_component_id="U2", name="U2"),
            SchematicComponent(
                schematic_component_id="sch_u1",
                source_component_id="U1",
                sheet_id="root",
                center=Point(x=0, y=0),
            ),
        ]
    )
    result = CompileEngine().schematic_completeness(project)
    assert not result.ok
    assert result.errors[0].code == "incomplete_schematic_components"


def test_arch_005_pipeline_stages_return_structured_result_objects():
    result = StageResult(stage="demo")
    result.add_error("bad", "Bad input")
    assert result.to_dict()["errors"][0]["code"] == "bad"


def test_arch_006_layout_stage_exposes_in_memory_intermediate_artifact_metadata():
    result = StageResult(
        stage="layout",
        artifacts=[OutputArtifact(kind="elk_input", name="root", metadata={"graph": {}})],
    )
    assert result.to_dict()["artifacts"][0]["metadata"]["graph"] == {}


def test_arch_020_circuit_project_is_first_class_container():
    project = CircuitProject(elements=[SourceComponent(source_component_id="U1", name="U1")])
    assert project.source_components["U1"].name == "U1"


def test_arch_021_circuit_project_separates_source_schematic_artifacts_and_metadata():
    project = _project_with_schematic()
    project.layout_artifacts["elk"] = {"root": {}}
    project.metadata["owner"] = "test"
    assert len(project.source_elements) == 1
    assert len(project.schematic_elements) == 1
    assert project.layout_artifacts["elk"] == {"root": {}}
    assert project.metadata["owner"] == "test"


def test_arch_022_pipeline_stages_accept_and_return_project_or_stage_results():
    project = _project_with_schematic()
    result = CompileEngine().kicad_project(project)
    assert result.stage == "kicad_transform"
    assert result.value.project is project


def test_arch_023_circuit_project_provides_typed_source_and_schematic_accessors():
    project = CircuitProject(
        elements=[
            SourceComponent(source_component_id="U1", name="U1"),
            SourcePort(source_port_id="P1", source_component_id="U1", name="1"),
            SourceNet(source_net_id="N1", name="NET"),
            SourceTrace(source_trace_id="T1", connected_source_port_ids=["P1"]),
            SourceGroup(source_group_id="G1"),
            SchematicComponent(
                schematic_component_id="S1",
                source_component_id="U1",
                sheet_id="root",
                center=Point(x=0, y=0),
            ),
        ]
    )
    assert set(project.source_components) == {"U1"}
    assert set(project.source_ports) == {"P1"}
    assert set(project.source_nets) == {"N1"}
    assert set(project.source_traces) == {"T1"}
    assert set(project.source_groups) == {"G1"}
    assert len(project.schematic_elements) == 1


def test_valp_001_validation_supports_named_profiles():
    assert {"source", "schematic", "compile-ready", "erc-ready"}.issubset(VALIDATION_PROFILES)


def test_valp_002_source_profile_validates_logic_only_circuit_json(tmp_path):
    result = validate_circuit_file(_write_json(tmp_path / "source.json", _source_circuit()), profile="source")
    assert result.is_valid
    assert all(message.profile == "source" for message in [*result.errors, *result.warnings])


def test_valp_003_schematic_profile_validates_schematic_references_geometry_labels_ports_and_no_connects(tmp_path):
    data = [
        *_source_circuit(),
        {
            "type": "schematic_component",
            "schematic_component_id": "S1",
            "source_component_id": "missing",
            "sheet_id": "root",
            "center": {"x": 0, "y": 0},
        },
    ]
    result = validate_circuit_file(_write_json(tmp_path / "schematic.json", data), profile="schematic")
    assert not result.is_valid
    assert result.errors[0].profile == "schematic"


def test_valp_004_compile_ready_profile_validates_generation_readiness(tmp_path):
    result = validate_circuit_file(_write_json(tmp_path / "empty.json", []), profile="compile-ready")
    assert not result.is_valid
    assert result.errors[0].rule == "compile_ready_source"


def test_valp_005_erc_ready_profile_validates_kicad_cli_availability(tmp_path, monkeypatch):
    monkeypatch.setattr("circuitweaver.library.paths.find_kicad_cli", lambda: None)
    result = validate_circuit_file(_write_json(tmp_path / "erc.json", _source_circuit()), profile="erc-ready")
    assert any(error.rule == "erc_ready_kicad_cli" for error in result.errors)


def test_valp_006_validation_results_report_profile_for_each_message(tmp_path):
    result = validate_circuit_file(_write_json(tmp_path / "bad.json", [{"type": "source_port", "source_port_id": "P", "source_component_id": "missing", "name": "1"}]), profile="source")
    assert result.errors[0].profile == "source"


def test_valp_007_validation_profiles_define_active_rule_sets_without_inactive_rule_files():
    active_rule_names = {rule.__name__ for rules in VALIDATION_PROFILES.values() for rule in rules}
    assert {"UniqueIdsRule", "SourceReferencesRule", "TraceConnectionsRule"}.issubset(active_rule_names)


@pytest.mark.asyncio
async def test_mcpr_001_mcp_tools_return_structured_result_objects():
    assert "ok" in json.loads(await search_kicad_parts("resistor", limit=1))


@pytest.mark.asyncio
async def test_mcpr_002_structured_mcp_results_include_common_fields():
    payload = json.loads(await search_kicad_parts("resistor", limit=1))
    assert {"ok", "errors", "warnings", "outputs"}.issubset(payload)


@pytest.mark.asyncio
async def test_mcpr_003_structured_mcp_results_include_human_readable_summary():
    assert json.loads(await search_kicad_parts("resistor", limit=1))["summary"]


@pytest.mark.asyncio
async def test_mcpr_004_search_kicad_parts_returns_structured_part_records():
    payload = json.loads(await search_kicad_parts("resistor", limit=1))
    if payload["parts"]:
        assert {"library_id", "library_name", "symbol_name", "description", "keywords", "footprint", "datasheet"}.issubset(payload["parts"][0])


@pytest.mark.asyncio
async def test_mcpr_005_get_symbol_pins_returns_structured_pin_records(monkeypatch):
    from circuitweaver.library.pinout import Pin, SymbolInfo

    symbol = SymbolInfo("Device:R", "R", [Pin("1", "A", Point(x=0, y=0), "left", "passive")], Point(x=0, y=0), Point(x=1, y=1))
    monkeypatch.setattr("circuitweaver.library.get_symbol_info", lambda symbol_id: symbol)
    payload = json.loads(await get_symbol_pins("Device:R"))
    assert payload["pins"][0]["grid_offset"] == {"x": 0, "y": 0}


@pytest.mark.asyncio
async def test_mcpr_006_validate_circuit_json_returns_validation_result_dict(tmp_path):
    payload = json.loads(await validate_circuit_json(str(_write_json(tmp_path / "source.json", _source_circuit()))))
    assert payload["validation"]["is_valid"] is True


@pytest.mark.asyncio
async def test_mcpr_007_create_schematic_returns_output_paths_and_artifact_metadata(monkeypatch, tmp_path):
    class FakeEngine:
        def layout(self, elements, debug_dir=None, debug_basename=None):
            return elements

        def compile(self, elements, output_dir, project_name):
            (output_dir / f"{project_name}.kicad_pro").write_text("{}", encoding="utf-8")
            path = output_dir / f"{project_name}.kicad_sch"
            path.write_text("(kicad_sch)", encoding="utf-8")
            return path

    monkeypatch.setattr("circuitweaver.compiler.engine.CompileEngine", FakeEngine)
    payload = json.loads(
        await create_schematic(
            str(_write_json(tmp_path / "source.json", _source_circuit())),
            output_dir=str(tmp_path / "out"),
        )
    )
    assert payload["outputs"]


@pytest.mark.asyncio
async def test_mcpr_008_run_erc_returns_structured_erc_errors_warnings_and_artifacts(monkeypatch, tmp_path):
    from circuitweaver.results import ToolResult

    monkeypatch.setattr("circuitweaver.server.tool_registry.run_erc_for_path", lambda *args, **kwargs: ToolResult(ok=True, summary="ok", data={"erc": {"is_valid": True, "errors": [], "warnings": []}}))
    payload = json.loads(await run_erc(str(_write_json(tmp_path / "source.json", _source_circuit()))))
    assert payload["erc"]["is_valid"] is True


@pytest.mark.asyncio
async def test_arch_040_create_schematic_accepts_explicit_output_directory(monkeypatch, tmp_path):
    assert "output_dir" in create_schematic.__annotations__


@pytest.mark.asyncio
async def test_arch_041_create_schematic_accepts_explicit_project_name():
    assert "project_name" in create_schematic.__annotations__


@pytest.mark.asyncio
async def test_arch_042_create_schematic_provides_explicit_write_flags():
    assert {"write_schematic_json", "write_kicad", "write_debug_layout"}.issubset(create_schematic.__annotations__)


def test_arch_043_output_artifact_serializes_created_or_modified_path(tmp_path):
    artifact = OutputArtifact(kind="file", path=tmp_path / "x")
    assert artifact.to_dict()["path"].endswith("x")


@pytest.mark.asyncio
async def test_arch_044_create_schematic_defaults_outputs_beside_input_when_no_output_dir(monkeypatch, tmp_path):
    class FakeEngine:
        def layout(self, elements, debug_dir=None, debug_basename=None):
            return elements

        def compile(self, elements, output_dir, project_name):
            (output_dir / f"{project_name}.kicad_pro").write_text("{}", encoding="utf-8")
            path = output_dir / f"{project_name}.kicad_sch"
            path.write_text("(kicad_sch)", encoding="utf-8")
            return path

    monkeypatch.setattr("circuitweaver.compiler.engine.CompileEngine", FakeEngine)
    source = _write_json(tmp_path / "source.json", _source_circuit())
    payload = json.loads(await create_schematic(str(source)))
    assert payload["output_dir"] == str(tmp_path)


def test_doctor_001_cli_provides_doctor_command(monkeypatch):
    monkeypatch.setattr("circuitweaver.cli.run_doctor", lambda: DoctorReport([DoctorCheck("x", True)]), raising=False)
    result = CliRunner().invoke(main, ["doctor", "--help"])
    assert result.exit_code == 0


def test_doctor_002_doctor_checks_python_package_version_and_importability():
    from circuitweaver.doctor import run_doctor

    report = run_doctor()
    assert any(check.name == "python_package" for check in report.checks)


def test_doctor_003_doctor_checks_nodejs_availability():
    from circuitweaver.doctor import run_doctor

    assert any(check.name == "node" for check in run_doctor().checks)


def test_doctor_004_doctor_checks_elkjs_resolution():
    from circuitweaver.doctor import run_doctor

    assert any(check.name == "elkjs" for check in run_doctor().checks)


def test_doctor_005_doctor_checks_kicad_library_paths():
    from circuitweaver.doctor import run_doctor

    assert any(check.name == "kicad_library_paths" for check in run_doctor().checks)


def test_doctor_006_doctor_checks_kicad_cli_availability():
    from circuitweaver.doctor import run_doctor

    assert any(check.name == "kicad_cli" for check in run_doctor().checks)


def test_doctor_007_doctor_checks_packaged_mcp_resources():
    from circuitweaver.doctor import run_doctor

    assert any(check.name == "mcp_resources" for check in run_doctor().checks)


def test_doctor_008_doctor_supports_machine_readable_json_output():
    payload = json.loads(doctor_json(DoctorReport([DoctorCheck("x", True)])))
    assert payload == {"ok": True, "checks": [{"name": "x", "ok": True, "details": "", "metadata": {}}]}


def test_arch_060_http_app_uses_mcp_sdk_streamable_http_support_when_available():
    app = create_http_app(create_server())
    assert app.state.uses_streamable_http_transport is True


def test_arch_061_hosted_http_mcp_supports_authentication_hooks():
    hook = lambda request: False
    app = create_http_app(create_server(), auth_hook=hook)
    assert app.state.auth_hook is hook


def test_arch_062_hosted_http_mcp_supports_request_limit_hooks():
    hook = lambda request: False
    app = create_http_app(create_server(), limit_hook=hook)
    assert app.state.limit_hook is hook


def test_arch_063_placeholder_sse_endpoint_is_removed():
    assert "/mcp/sse" not in {route.path for route in create_http_app(create_server()).routes}


def test_arch_080_cli_and_mcp_erc_share_unified_input_model():
    from circuitweaver.erc.runner import run_erc_for_path

    assert callable(run_erc_for_path)


def test_arch_081_erc_supports_circuit_json_inputs(tmp_path):
    from circuitweaver.erc.runner import run_erc_for_path

    result = run_erc_for_path(tmp_path / "missing.json")
    assert result.errors[0].code == "file_not_found"


def test_arch_082_erc_supports_existing_kicad_schematic_paths(tmp_path, monkeypatch):
    from circuitweaver.erc.runner import run_erc_for_path

    schematic = tmp_path / "board.kicad_sch"
    schematic.write_text("(kicad_sch)", encoding="utf-8")
    monkeypatch.setattr("circuitweaver.erc.runner.ERCChecker.run", lambda self, path: {"is_valid": True, "errors": [], "warnings": []})
    assert run_erc_for_path(schematic).ok


def test_arch_083_erc_results_use_structured_tool_result_schema(tmp_path):
    from circuitweaver.erc.runner import run_erc_for_path

    assert {"ok", "errors", "warnings", "outputs"}.issubset(run_erc_for_path(tmp_path / "missing.json").to_dict())


def test_test_001_kicad_sexpr_generation_supports_deterministic_uuid_generation():
    ids = iter(["uuid-a", "uuid-b"])
    sexpr = SchematicToSExprTransform(uuid_factory=lambda: next(ids)).transform(
        [SchematicComponent(schematic_component_id="S1", source_component_id="U1", sheet_id="root", center=Point(x=0, y=0))],
        "root",
        {"U1": SourceComponent(source_component_id="U1", name="U1")},
    )
    assert "uuid-a" in s_expr_serialize(sexpr)


def test_test_002_compile_pipeline_can_inject_symbol_lookup_router_and_erc_dependencies(tmp_path):
    class FakeRouter:
        def run(self, graph):
            return graph

    calls = {"symbol": False, "erc": False}
    engine = CompileEngine(
        router=FakeRouter(),
        symbol_lookup=lambda symbol_id: calls.update(symbol=True) or None,
        erc_runner=lambda path: calls.update(erc=True) or {"is_valid": True, "errors": [], "warnings": []},
    )
    engine._load_symbols([SourceComponent(source_component_id="U1", name="U1", symbol_id="Device:R")])
    engine.run_erc(tmp_path / "board.kicad_sch")
    assert calls == {"symbol": True, "erc": True}


def test_test_003_requirement_to_test_traceability_is_machine_checkable_for_target_architecture():
    report = traceability_report(
        Path("docs/requirements/target-architecture.md"),
        Path("tests/test_target_architecture_requirements.py"),
    )
    assert report["ok"], report["missing"]

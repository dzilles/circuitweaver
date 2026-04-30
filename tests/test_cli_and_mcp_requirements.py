"""Requirement-traceable tests for docs/requirements/cli-and-mcp.md."""

# ruff: noqa: ARG001, ARG002, ARG005

import builtins
import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from mcp.types import (
    CallToolRequest,
    CallToolRequestParams,
    GetPromptRequest,
    GetPromptRequestParams,
    ListPromptsRequest,
    ListResourcesRequest,
    ListToolsRequest,
    ReadResourceRequest,
    ReadResourceRequestParams,
)

from circuitweaver.cli import main
from circuitweaver.server.http_transport import _handle_mcp_request, create_http_app
from circuitweaver.server.mcp_server import _run_http, _run_stdio, create_server, run_server
from circuitweaver.server.tool_registry import TOOL_REGISTRY
from circuitweaver.types import Point, SchematicText


def _runner() -> CliRunner:
    return CliRunner()


def _write_json(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _source_only_circuit() -> list[dict[str, object]]:
    return [
        {
            "type": "source_component",
            "source_component_id": "src_r1",
            "name": "R1",
        }
    ]


def _invalid_circuit() -> list[dict[str, object]]:
    return [
        {
            "type": "source_port",
            "source_port_id": "p1",
            "source_component_id": "missing",
            "name": "1",
        }
    ]


def _tools_result(server):
    req = ListToolsRequest(method="tools/list")
    return server.request_handlers[ListToolsRequest](req)


async def _list_tools(server):
    response = await _tools_result(server)
    return response.root.tools


async def _call_tool(server, name: str, arguments: dict[str, object]):
    req = CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(name=name, arguments=arguments),
    )
    return await server.request_handlers[CallToolRequest](req)


async def _list_resources(server):
    req = ListResourcesRequest(method="resources/list")
    response = await server.request_handlers[ListResourcesRequest](req)
    return response.root.resources


async def _read_resource(server, uri: str):
    req = ReadResourceRequest(
        method="resources/read",
        params=ReadResourceRequestParams(uri=uri),
    )
    return await server.request_handlers[ReadResourceRequest](req)


async def _list_prompts(server):
    req = ListPromptsRequest(method="prompts/list")
    response = await server.request_handlers[ListPromptsRequest](req)
    return response.root.prompts


async def _get_prompt(server, name: str):
    req = GetPromptRequest(
        method="prompts/get",
        params=GetPromptRequestParams(name=name, arguments=None),
    )
    return await server.request_handlers[GetPromptRequest](req)


def _tool_schema(tool_name: str) -> dict[str, object]:
    return TOOL_REGISTRY[tool_name].to_mcp_tool().inputSchema


def test_cli_001_root_command_is_named_circuitweaver():
    result = _runner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "CircuitWeaver" in result.output


def test_cli_002_version_reports_package_version():
    from circuitweaver import __version__

    result = _runner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_cli_003_validate_input_file_validates_circuit_json(tmp_path):
    circuit_file = _write_json(tmp_path / "valid.json", _source_only_circuit())
    result = _runner().invoke(main, ["validate", str(circuit_file)])
    assert result.exit_code == 0
    assert "SUCCESS" in result.output


def test_cli_004_validate_supports_text_and_json_output_formats(tmp_path):
    circuit_file = _write_json(tmp_path / "valid.json", _source_only_circuit())
    text_result = _runner().invoke(main, ["validate", str(circuit_file), "--output-format", "text"])
    json_result = _runner().invoke(main, ["validate", str(circuit_file), "--output-format", "json"])
    assert text_result.exit_code == 0
    assert json_result.exit_code == 0
    assert json.loads(json_result.output)["is_valid"] is True


def test_cli_005_validate_exits_1_when_validation_has_errors(tmp_path):
    circuit_file = _write_json(tmp_path / "invalid.json", _invalid_circuit())
    result = _runner().invoke(main, ["validate", str(circuit_file)])
    assert result.exit_code == 1
    assert "FAILED" in result.stderr


def test_cli_006_compile_parses_json_and_writes_kicad_files_through_compile_engine(
    monkeypatch, tmp_path
):
    calls = {}

    class FakeCompileEngine:
        def compile(self, elements, output_dir, project_name):
            calls["elements"] = elements
            calls["output_dir"] = output_dir
            calls["project_name"] = project_name
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / f"{project_name}.kicad_sch"
            output_file.write_text("(kicad_sch)", encoding="utf-8")
            return output_file

    import circuitweaver.compiler

    monkeypatch.setattr(circuitweaver.compiler, "CompileEngine", FakeCompileEngine)
    circuit_file = _write_json(tmp_path / "circuit.json", _source_only_circuit())
    result = _runner().invoke(main, ["compile", str(circuit_file), "-o", str(tmp_path / "out")])
    assert result.exit_code == 0
    assert calls["elements"][0].source_component_id == "src_r1"
    assert calls["output_dir"] == tmp_path / "out"


def test_cli_007_compile_defaults_output_dir_to_output(monkeypatch, tmp_path):
    calls = {}

    class FakeCompileEngine:
        def compile(self, elements, output_dir, project_name):
            calls["output_dir"] = output_dir
            output_dir.mkdir(parents=True, exist_ok=True)
            return output_dir / f"{project_name}.kicad_sch"

    import circuitweaver.compiler

    monkeypatch.setattr(circuitweaver.compiler, "CompileEngine", FakeCompileEngine)
    circuit_file = _write_json(tmp_path / "circuit.json", _source_only_circuit())
    with _runner().isolated_filesystem(temp_dir=tmp_path):
        result = _runner().invoke(main, ["compile", str(circuit_file)])
    assert result.exit_code == 0
    assert calls["output_dir"] == Path("output")


def test_cli_008_compile_defaults_project_name_to_project(monkeypatch, tmp_path):
    calls = {}

    class FakeCompileEngine:
        def compile(self, elements, output_dir, project_name):
            calls["project_name"] = project_name
            output_dir.mkdir(parents=True, exist_ok=True)
            return output_dir / f"{project_name}.kicad_sch"

    import circuitweaver.compiler

    monkeypatch.setattr(circuitweaver.compiler, "CompileEngine", FakeCompileEngine)
    circuit_file = _write_json(tmp_path / "circuit.json", _source_only_circuit())
    result = _runner().invoke(main, ["compile", str(circuit_file), "-o", str(tmp_path / "out")])
    assert result.exit_code == 0
    assert calls["project_name"] == "project"


def test_cli_009_compile_supports_output_dir_and_name_options(monkeypatch, tmp_path):
    calls = {}

    class FakeCompileEngine:
        def compile(self, elements, output_dir, project_name):
            calls.update(output_dir=output_dir, project_name=project_name)
            output_dir.mkdir(parents=True, exist_ok=True)
            return output_dir / f"{project_name}.kicad_sch"

    import circuitweaver.compiler

    monkeypatch.setattr(circuitweaver.compiler, "CompileEngine", FakeCompileEngine)
    circuit_file = _write_json(tmp_path / "circuit.json", _source_only_circuit())
    result = _runner().invoke(
        main,
        ["compile", str(circuit_file), "--output-dir", str(tmp_path / "custom"), "--name", "board"],
    )
    assert result.exit_code == 0
    assert calls == {"output_dir": tmp_path / "custom", "project_name": "board"}


def test_cli_010_compile_exits_1_and_prints_traceback_on_failure(monkeypatch, tmp_path):
    class FakeCompileEngine:
        def compile(self, elements, output_dir, project_name):
            raise RuntimeError("compile failed")

    import circuitweaver.compiler

    monkeypatch.setattr(circuitweaver.compiler, "CompileEngine", FakeCompileEngine)
    circuit_file = _write_json(tmp_path / "circuit.json", _source_only_circuit())
    result = _runner().invoke(main, ["compile", str(circuit_file)])
    assert result.exit_code == 1
    assert "Traceback" in result.stderr
    assert "compile failed" in result.output


def test_cli_011_erc_runs_kicad_erc_through_erc_checker(monkeypatch, tmp_path):
    calls = {}

    class FakeERCChecker:
        def run(self, path):
            calls["path"] = path
            return {"is_valid": True, "errors": [], "warnings": []}

    import circuitweaver.erc.checker

    monkeypatch.setattr(circuitweaver.erc.checker, "ERCChecker", FakeERCChecker)
    schematic = tmp_path / "board.kicad_sch"
    schematic.write_text("(kicad_sch)", encoding="utf-8")
    result = _runner().invoke(main, ["erc", str(schematic)])
    assert result.exit_code == 0
    assert calls["path"] == schematic


def test_cli_012_erc_exits_1_if_erc_execution_raises(monkeypatch, tmp_path):
    class FakeERCChecker:
        def run(self, path):
            raise RuntimeError("erc failed")

    import circuitweaver.erc.checker

    monkeypatch.setattr(circuitweaver.erc.checker, "ERCChecker", FakeERCChecker)
    schematic = tmp_path / "board.kicad_sch"
    schematic.write_text("(kicad_sch)", encoding="utf-8")
    result = _runner().invoke(main, ["erc", str(schematic)])
    assert result.exit_code == 1
    assert "FAILED to run ERC" in result.output


def test_cli_013_search_query_searches_kicad_parts(monkeypatch):
    from circuitweaver.library.search import PartInfo

    monkeypatch.setattr(
        "circuitweaver.library.search_parts",
        lambda query, limit=10: [PartInfo("Device:R", "Device", "R", "Resistor")],
    )
    result = _runner().invoke(main, ["search", "resistor"])
    assert result.exit_code == 0
    assert "Device:R" in result.output


def test_cli_014_search_supports_limit_defaulting_to_10(monkeypatch):
    calls = {}

    def fake_search_parts(query, limit=10):
        calls["limit"] = limit
        return []

    monkeypatch.setattr("circuitweaver.library.search_parts", fake_search_parts)
    default_result = _runner().invoke(main, ["search", "resistor"])
    option_result = _runner().invoke(main, ["search", "resistor", "--limit", "3"])
    assert default_result.exit_code == 0
    assert option_result.exit_code == 0
    assert calls["limit"] == 3


def test_cli_015_pins_prints_symbol_pin_number_name_and_electrical_type(monkeypatch):
    from circuitweaver.library.pinout import Pin, SymbolInfo

    symbol = SymbolInfo(
        symbol_id="Device:R",
        name="R",
        pins=[Pin("1", "A", None, "left", "passive")],
        bounding_box_min=None,
        bounding_box_max=None,
    )
    monkeypatch.setattr("circuitweaver.library.get_symbol_info", lambda symbol_id: symbol)
    result = _runner().invoke(main, ["pins", "Device:R"])
    assert result.exit_code == 0
    assert "1" in result.output
    assert "A" in result.output
    assert "passive" in result.output


def test_cli_016_pins_exits_1_when_symbol_lookup_raises_value_error(monkeypatch):
    def raise_value_error(symbol_id):
        raise ValueError("missing symbol")

    monkeypatch.setattr("circuitweaver.library.get_symbol_info", raise_value_error)
    result = _runner().invoke(main, ["pins", "Missing:Symbol"])
    assert result.exit_code == 1
    assert "missing symbol" in result.stderr


def test_cli_017_serve_runs_the_mcp_server(monkeypatch):
    calls = {}

    monkeypatch.setattr("circuitweaver.server.mcp_server.create_server", lambda enabled_tools=None: "server")

    def fake_run_server(server, transport, port, host):
        calls.update(server=server, transport=transport, port=port, host=host)

    monkeypatch.setattr("circuitweaver.server.mcp_server.run_server", fake_run_server)
    result = _runner().invoke(main, ["serve"])
    assert result.exit_code == 0
    assert calls["server"] == "server"


def test_cli_018_serve_supports_stdio_and_http_transport_defaulting_to_stdio(monkeypatch):
    calls = []

    monkeypatch.setattr("circuitweaver.server.mcp_server.create_server", lambda enabled_tools=None: "server")
    monkeypatch.setattr(
        "circuitweaver.server.mcp_server.run_server",
        lambda server, transport, port, host: calls.append(transport),
    )
    default_result = _runner().invoke(main, ["serve"])
    http_result = _runner().invoke(main, ["serve", "--transport", "http"])
    assert default_result.exit_code == 0
    assert http_result.exit_code == 0
    assert calls == ["stdio", "http"]


def test_cli_019_serve_supports_tools_comma_separated_allowlist(monkeypatch):
    calls = {}

    def fake_create_server(enabled_tools=None):
        calls["enabled_tools"] = enabled_tools
        return "server"

    monkeypatch.setattr("circuitweaver.server.mcp_server.create_server", fake_create_server)
    monkeypatch.setattr("circuitweaver.server.mcp_server.run_server", lambda *args, **kwargs: None)
    result = _runner().invoke(main, ["serve", "--tools", "validate_circuit_json,run_erc"])
    assert result.exit_code == 0
    assert calls["enabled_tools"] == ["validate_circuit_json", "run_erc"]


def test_cli_020_serve_supports_port_defaulting_to_3000(monkeypatch):
    calls = []

    monkeypatch.setattr("circuitweaver.server.mcp_server.create_server", lambda enabled_tools=None: "server")
    monkeypatch.setattr(
        "circuitweaver.server.mcp_server.run_server",
        lambda server, transport, port, host: calls.append(port),
    )
    default_result = _runner().invoke(main, ["serve"])
    custom_result = _runner().invoke(main, ["serve", "--port", "1234"])
    assert default_result.exit_code == 0
    assert custom_result.exit_code == 0
    assert calls == [3000, 1234]


def test_cli_021_serve_supports_host_defaulting_to_localhost(monkeypatch):
    calls = []

    monkeypatch.setattr("circuitweaver.server.mcp_server.create_server", lambda enabled_tools=None: "server")
    monkeypatch.setattr(
        "circuitweaver.server.mcp_server.run_server",
        lambda server, transport, port, host: calls.append(host),
    )
    default_result = _runner().invoke(main, ["serve"])
    custom_result = _runner().invoke(main, ["serve", "--host", "0.0.0.0"])
    assert default_result.exit_code == 0
    assert custom_result.exit_code == 0
    assert calls == ["localhost", "0.0.0.0"]


def test_cli_022_info_prints_package_version_and_detected_kicad_library_paths(monkeypatch, tmp_path):
    from circuitweaver.library.paths import LibraryPaths

    monkeypatch.chdir(tmp_path)
    symbols = Path("symbols")
    footprints = Path("footprints")
    symbols.mkdir()
    footprints.mkdir()
    monkeypatch.setattr(
        "circuitweaver.cli.get_library_paths",
        lambda: LibraryPaths(symbols=symbols, footprints=footprints),
    )
    result = _runner().invoke(main, ["info"])
    assert result.exit_code == 0
    assert "Version" in result.output
    assert str(symbols) in result.output
    assert str(footprints) in result.output


def test_cli_023_python_m_circuitweaver_uses_same_cli_entry_point():
    import circuitweaver.__main__
    import circuitweaver.cli

    assert circuitweaver.__main__.main is circuitweaver.cli.main


def test_mcp_001_server_name_is_circuitweaver():
    assert create_server().name == "circuitweaver"


@pytest.mark.asyncio
async def test_mcp_002_without_enabled_tools_exposes_all_tool_registry_tools():
    tools = await _list_tools(create_server())
    assert {tool.name for tool in tools} == set(TOOL_REGISTRY)


@pytest.mark.asyncio
async def test_mcp_003_enabled_tools_exposes_only_matching_registry_tools():
    tools = await _list_tools(create_server(enabled_tools=["validate_circuit_json", "run_erc"]))
    assert {tool.name for tool in tools} == {"validate_circuit_json", "run_erc"}


@pytest.mark.asyncio
async def test_mcp_004_unknown_enabled_tool_names_are_silently_ignored():
    tools = await _list_tools(create_server(enabled_tools=["validate_circuit_json", "missing_tool"]))
    assert {tool.name for tool in tools} == {"validate_circuit_json"}


@pytest.mark.asyncio
async def test_mcp_005_list_tools_returns_tool_definitions_from_active_handlers():
    tools = await _list_tools(create_server(enabled_tools=["validate_circuit_json"]))
    assert len(tools) == 1
    assert tools[0].name == "validate_circuit_json"
    assert tools[0].inputSchema["required"] == ["file_path"]


@pytest.mark.asyncio
async def test_mcp_006_unknown_tool_call_returns_unknown_tool_text():
    response = await _call_tool(create_server(), "missing_tool", {})
    assert response.root.content[0].text == "Unknown tool: missing_tool"


@pytest.mark.asyncio
async def test_mcp_007_tool_handler_exceptions_return_error_text(monkeypatch):
    async def raise_error(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(TOOL_REGISTRY["validate_circuit_json"], "handler", raise_error)
    response = await _call_tool(create_server(), "validate_circuit_json", {"file_path": "x"})
    assert response.root.content[0].text.startswith("Error:")
    assert "boom" in response.root.content[0].text


def test_mcp_008_tool_parameters_convert_to_json_schema_properties_and_required_list():
    schema = _tool_schema("create_schematic")
    assert schema["type"] == "object"
    assert schema["properties"]["file_path"]["type"] == "string"
    assert schema["properties"]["debug"]["default"] is False
    assert schema["required"] == ["file_path"]


def test_mcp_020_search_kicad_parts_accepts_query_and_optional_limit():
    schema = _tool_schema("search_kicad_parts")
    assert set(schema["properties"]) == {"query", "limit"}
    assert schema["required"] == ["query"]
    assert schema["properties"]["limit"]["default"] == 10


@pytest.mark.asyncio
async def test_mcp_021_search_kicad_parts_returns_human_readable_results_or_no_results():
    response = await _call_tool(create_server(), "search_kicad_parts", {"query": "resistor", "limit": 1})
    text = response.root.content[0].text
    assert "Found" in text or "No results found" in text


def test_mcp_022_get_symbol_pins_accepts_symbol_id():
    schema = _tool_schema("get_symbol_pins")
    assert set(schema["properties"]) == {"symbol_id"}
    assert schema["required"] == ["symbol_id"]


@pytest.mark.asyncio
async def test_mcp_023_get_symbol_pins_returns_markdown_table(monkeypatch):
    from circuitweaver.library.pinout import Pin, SymbolInfo

    symbol = SymbolInfo(
        symbol_id="Device:R",
        name="R",
        pins=[Pin("1", "A", Point(x=0, y=0), "left", "passive")],
        bounding_box_min=Point(x=0, y=0),
        bounding_box_max=Point(x=10, y=10),
    )
    monkeypatch.setattr("circuitweaver.library.get_symbol_info", lambda symbol_id: symbol)
    response = await _call_tool(create_server(), "get_symbol_pins", {"symbol_id": "Device:R"})
    text = response.root.content[0].text
    assert "| Pin #" in text
    assert "| 1" in text
    assert "passive" in text


@pytest.mark.asyncio
async def test_mcp_024_get_symbol_pins_returns_error_string_when_lookup_fails(monkeypatch):
    def raise_value_error(symbol_id):
        raise ValueError("missing")

    monkeypatch.setattr("circuitweaver.library.get_symbol_info", raise_value_error)
    response = await _call_tool(create_server(), "get_symbol_pins", {"symbol_id": "Missing:Symbol"})
    assert response.root.content[0].text.startswith("Error:")


def test_mcp_025_validate_circuit_json_accepts_file_path():
    schema = _tool_schema("validate_circuit_json")
    assert set(schema["properties"]) == {"file_path"}
    assert schema["required"] == ["file_path"]


@pytest.mark.asyncio
async def test_mcp_026_validate_circuit_json_rejects_invalid_missing_and_non_file_paths(tmp_path):
    server = create_server()
    missing = await _call_tool(server, "validate_circuit_json", {"file_path": str(tmp_path / "missing.json")})
    non_file = await _call_tool(server, "validate_circuit_json", {"file_path": str(tmp_path)})
    assert "File not found" in missing.root.content[0].text
    assert "Not a file" in non_file.root.content[0].text


@pytest.mark.asyncio
async def test_mcp_027_validate_circuit_json_returns_success_when_no_errors(tmp_path):
    circuit_file = _write_json(tmp_path / "valid.json", _source_only_circuit())
    response = await _call_tool(create_server(), "validate_circuit_json", {"file_path": str(circuit_file)})
    assert "SUCCESS" in response.root.content[0].text


@pytest.mark.asyncio
async def test_mcp_028_validate_circuit_json_returns_failed_and_errors_when_errors_exist(tmp_path):
    circuit_file = _write_json(tmp_path / "invalid.json", _invalid_circuit())
    response = await _call_tool(create_server(), "validate_circuit_json", {"file_path": str(circuit_file)})
    text = response.root.content[0].text
    assert "FAILED" in text
    assert "non-existent source_component" in text


def test_mcp_029_create_schematic_accepts_file_path_and_optional_debug():
    schema = _tool_schema("create_schematic")
    assert set(schema["properties"]) == {"file_path", "debug"}
    assert schema["required"] == ["file_path"]
    assert schema["properties"]["debug"]["default"] is False


@pytest.mark.asyncio
async def test_mcp_030_create_schematic_reads_json_runs_layout_and_writes_outputs(monkeypatch, tmp_path):
    class FakeCompileEngine:
        def layout(self, elements, debug_dir=None, debug_basename=None):
            return [
                *_source_only_circuit_elements(elements),
                SchematicText(
                    schematic_text_id="txt1",
                    sheet_id="root",
                    position=Point(x=0, y=0),
                    text="hello",
                ),
            ]

        def compile(self, elements, output_dir, project_name):
            (output_dir / f"{project_name}.kicad_sch").write_text("(kicad_sch)", encoding="utf-8")
            (output_dir / f"{project_name}.kicad_pro").write_text("{}", encoding="utf-8")
            return output_dir / f"{project_name}.kicad_sch"

    def _source_only_circuit_elements(elements):
        return elements

    monkeypatch.setattr("circuitweaver.compiler.engine.CompileEngine", FakeCompileEngine)
    circuit_file = _write_json(tmp_path / "demo.json", _source_only_circuit())
    response = await _call_tool(create_server(), "create_schematic", {"file_path": str(circuit_file)})
    assert "SUCCESS" in response.root.content[0].text
    assert (tmp_path / "demo_schematic.json").exists()
    assert (tmp_path / "demo.kicad_sch").exists()
    assert (tmp_path / "demo.kicad_pro").exists()


@pytest.mark.asyncio
async def test_mcp_031_create_schematic_debug_true_writes_elk_debug_files(monkeypatch, tmp_path):
    class FakeCompileEngine:
        def layout(self, elements, debug_dir=None, debug_basename=None):
            if debug_dir and debug_basename:
                (debug_dir / f"{debug_basename}_layout_in.json").write_text("{}", encoding="utf-8")
                (debug_dir / f"{debug_basename}_layout_out.json").write_text("{}", encoding="utf-8")
            return [
                SchematicText(
                    schematic_text_id="txt1",
                    sheet_id="root",
                    position=Point(x=0, y=0),
                    text="hello",
                )
            ]

        def compile(self, elements, output_dir, project_name):
            (output_dir / f"{project_name}.kicad_sch").write_text("(kicad_sch)", encoding="utf-8")
            (output_dir / f"{project_name}.kicad_pro").write_text("{}", encoding="utf-8")
            return output_dir / f"{project_name}.kicad_sch"

    monkeypatch.setattr("circuitweaver.compiler.engine.CompileEngine", FakeCompileEngine)
    circuit_file = _write_json(tmp_path / "demo.json", _source_only_circuit())
    response = await _call_tool(
        create_server(), "create_schematic", {"file_path": str(circuit_file), "debug": True}
    )
    assert "layout_in" in response.root.content[0].text
    assert (tmp_path / "demo_layout_in.json").exists()
    assert (tmp_path / "demo_layout_out.json").exists()


def test_mcp_032_run_erc_accepts_file_path():
    schema = _tool_schema("run_erc")
    assert set(schema["properties"]) == {"file_path"}
    assert schema["required"] == ["file_path"]


@pytest.mark.asyncio
async def test_mcp_033_run_erc_reads_json_compiles_temporary_and_returns_status(monkeypatch, tmp_path):
    class FakeCompileEngine:
        def compile(self, elements, output_dir, project_name):
            output_file = output_dir / f"{project_name}.kicad_sch"
            output_file.write_text("(kicad_sch)", encoding="utf-8")
            return output_file

        def run_erc(self, schematic_path):
            return {"is_valid": True, "errors": [], "warnings": []}

    monkeypatch.setattr("circuitweaver.compiler.engine.CompileEngine", FakeCompileEngine)
    circuit_file = _write_json(tmp_path / "demo.json", _source_only_circuit())
    response = await _call_tool(create_server(), "run_erc", {"file_path": str(circuit_file)})
    assert "SUCCESS: ERC passed" in response.root.content[0].text


@pytest.mark.asyncio
async def test_mcp_034_mcp_does_not_expose_generic_file_editing_tools():
    tools = await _list_tools(create_server())
    names = {tool.name for tool in tools}
    assert {"read_file", "write_file", "edit_file"}.isdisjoint(names)


@pytest.mark.asyncio
async def test_mcp_040_server_exposes_docs_readme_resource():
    resources = await _list_resources(create_server())
    assert "circuitweaver://docs/readme" in {str(resource.uri) for resource in resources}


@pytest.mark.asyncio
async def test_mcp_041_server_exposes_docs_install_resource():
    resources = await _list_resources(create_server())
    assert "circuitweaver://docs/install" in {str(resource.uri) for resource in resources}


@pytest.mark.asyncio
async def test_mcp_042_server_exposes_docs_mcp_workflow_resource():
    resources = await _list_resources(create_server())
    assert "circuitweaver://docs/mcp-workflow" in {str(resource.uri) for resource in resources}


@pytest.mark.asyncio
async def test_mcp_043_server_exposes_tools_reference_resource():
    resources = await _list_resources(create_server())
    assert "circuitweaver://tools/reference" in {str(resource.uri) for resource in resources}


@pytest.mark.asyncio
async def test_mcp_044_server_exposes_circuit_json_spec_resource():
    resources = await _list_resources(create_server())
    assert "circuitweaver://docs/circuit-json-spec" in {str(resource.uri) for resource in resources}


@pytest.mark.asyncio
async def test_mcp_045_server_exposes_troubleshooting_resource():
    resources = await _list_resources(create_server())
    assert "circuitweaver://docs/troubleshooting" in {str(resource.uri) for resource in resources}


@pytest.mark.asyncio
async def test_mcp_046_server_exposes_examples_simple_led_resource():
    resources = await _list_resources(create_server())
    assert "circuitweaver://examples/simple-led" in {str(resource.uri) for resource in resources}


@pytest.mark.asyncio
async def test_mcp_047_docs_examples_aliases_simple_led_example():
    server = create_server()
    direct = await _read_resource(server, "circuitweaver://examples/simple-led")
    alias = await _read_resource(server, "circuitweaver://docs/examples")
    assert direct.root.contents[0].text == alias.root.contents[0].text


@pytest.mark.asyncio
async def test_mcp_048_unknown_resource_uris_raise_value_error():
    with pytest.raises(ValueError, match="Unknown resource"):
        await _read_resource(create_server(), "circuitweaver://missing")


@pytest.mark.asyncio
async def test_mcp_049_tools_reference_is_generated_from_active_tool_set():
    server = create_server(enabled_tools=["validate_circuit_json"])
    response = await _read_resource(server, "circuitweaver://tools/reference")
    text = response.root.contents[0].text
    assert "`validate_circuit_json`" in text
    assert "`run_erc`" not in text


@pytest.mark.asyncio
async def test_mcp_050_resource_loading_reads_packaged_or_source_files():
    response = await _read_resource(create_server(), "circuitweaver://docs/mcp-workflow")
    assert "# CircuitWeaver MCP Workflow" in response.root.contents[0].text


@pytest.mark.asyncio
async def test_mcp_060_server_exposes_one_prompt_named_design_guidelines():
    prompts = await _list_prompts(create_server())
    assert [prompt.name for prompt in prompts] == ["design-guidelines"]


@pytest.mark.asyncio
async def test_mcp_061_design_guidelines_instructs_clients_to_load_resources():
    response = await _get_prompt(create_server(), "design-guidelines")
    text = response.root.messages[0].content.text
    assert "circuitweaver://docs/mcp-workflow" in text
    assert "circuitweaver://tools/reference" in text
    assert "circuitweaver://docs/circuit-json-spec" in text


@pytest.mark.asyncio
async def test_mcp_062_design_guidelines_instructs_client_native_file_tools():
    response = await _get_prompt(create_server(), "design-guidelines")
    assert "client's normal file tools" in response.root.messages[0].content.text


@pytest.mark.asyncio
async def test_mcp_063_design_guidelines_instructs_circuitweaver_specific_tools_only():
    response = await _get_prompt(create_server(), "design-guidelines")
    assert "CircuitWeaver-specific actions" in response.root.messages[0].content.text


@pytest.mark.asyncio
async def test_mcp_064_unknown_prompt_names_raise_value_error():
    with pytest.raises(ValueError, match="Unknown prompt"):
        await _get_prompt(create_server(), "missing")


@pytest.mark.asyncio
async def test_mcp_070_stdio_transport_uses_stdio_server(monkeypatch):
    calls = {}

    class FakeStreams:
        async def __aenter__(self):
            calls["entered"] = True
            return "read", "write"

        async def __aexit__(self, exc_type, exc, tb):
            calls["exited"] = True

    class FakeServer:
        def create_initialization_options(self):
            return "options"

        async def run(self, read_stream, write_stream, options):
            calls["run"] = (read_stream, write_stream, options)

    monkeypatch.setattr("circuitweaver.server.mcp_server.stdio_server", lambda: FakeStreams())
    await _run_stdio(FakeServer())
    assert calls["entered"] is True
    assert calls["run"] == ("read", "write", "options")


def test_mcp_071_http_transport_imports_uvicorn_and_create_http_app(monkeypatch):
    calls = {}

    monkeypatch.setattr("uvicorn.run", lambda app, host, port: calls.update(app=app))
    _run_http(create_server(), "127.0.0.1", 3000)
    assert calls["app"].title == "CircuitWeaver MCP Server"


def test_mcp_072_http_transport_import_failure_mentions_http_extra(monkeypatch):
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "uvicorn":
            raise ImportError("missing uvicorn")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ImportError, match=r"circuitweaver\[http\]"):
        _run_http(create_server(), "127.0.0.1", 3000)


def test_mcp_073_http_transport_runs_uvicorn_with_host_and_port(monkeypatch):
    calls = {}

    monkeypatch.setattr(
        "uvicorn.run",
        lambda app, host, port: calls.update(host=host, port=port),
    )
    _run_http(create_server(), "0.0.0.0", 4321)
    assert calls == {"host": "0.0.0.0", "port": 4321}


def test_mcp_074_unsupported_transport_names_raise_value_error():
    with pytest.raises(ValueError, match="Unknown transport"):
        run_server(create_server(), transport="bad")


def test_mcp_075_custom_http_app_exposes_root_and_health_endpoints():
    app = create_http_app(create_server())
    route_paths = {route.path for route in app.routes}
    assert {"/", "/health"}.issubset(route_paths)


def test_mcp_076_custom_http_app_exposes_post_mcp_endpoint():
    app = create_http_app(create_server())
    routes = {(route.path, tuple(sorted(getattr(route, "methods", [])))) for route in app.routes}
    assert any(path == "/mcp" and "POST" in methods for path, methods in routes)


def test_mcp_077_custom_http_app_exposes_sse_endpoint():
    app = create_http_app(create_server())
    route_paths = {route.path for route in app.routes}
    assert "/mcp/sse" in route_paths


@pytest.mark.asyncio
async def test_mcp_078_http_json_rpc_handler_implements_tools_and_resources_methods():
    server = create_server()
    tools = json.loads(await _handle_mcp_request(server, {"method": "tools/list", "id": 1}))
    tool_call = json.loads(
        await _handle_mcp_request(
            server,
            {"method": "tools/call", "params": {"name": "search_kicad_parts", "arguments": {"query": "unlikely-part-name"}}, "id": 2},
        )
    )
    resources = json.loads(await _handle_mcp_request(server, {"method": "resources/list", "id": 3}))
    resource = json.loads(
        await _handle_mcp_request(
            server,
            {"method": "resources/read", "params": {"uri": "circuitweaver://tools/reference"}, "id": 4},
        )
    )
    assert "tools" in tools["result"]
    assert "content" in tool_call["result"]
    assert "resources" in resources["result"]
    assert "contents" in resource["result"]


@pytest.mark.asyncio
async def test_mcp_079_unsupported_http_json_rpc_methods_return_method_not_found_error():
    response = json.loads(await _handle_mcp_request(create_server(), {"method": "missing", "id": 1}))
    assert response["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_mcp_080_http_handler_exceptions_return_internal_error(monkeypatch):
    async def raise_error(req):
        raise RuntimeError("broken")

    server = create_server()
    monkeypatch.setitem(server.request_handlers, ListToolsRequest, raise_error)
    response = json.loads(await _handle_mcp_request(server, {"method": "tools/list", "id": 1}))
    assert response["error"]["code"] == -32603
    assert "broken" in response["error"]["message"]

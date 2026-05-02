"""Tool registry for CircuitWeaver MCP server.

This module defines the registry of all available tools and their handlers.
"""

import json
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp.types import Tool

from circuitweaver.erc.runner import run_erc_for_path
from circuitweaver.results import Diagnostic, OutputArtifact, ToolResult


@dataclass
class ToolParameter:
    """Definition of a tool parameter."""

    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None
    enum: list[str] | None = None


@dataclass
class ToolHandler:
    """Handler for an MCP tool."""

    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)
    handler: Callable[..., Coroutine[Any, Any, str]] | None = None

    def to_mcp_tool(self) -> Tool:
        """Convert to MCP Tool definition."""
        properties = {}
        required = []

        for param in self.parameters:
            prop: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default

            properties[param.name] = prop

            if param.required:
                required.append(param.name)

        return Tool(
            name=self.name,
            description=self.description,
            inputSchema={
                "type": "object",
                "properties": properties,
                "required": required,
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> str:
        """Execute the tool with given arguments."""
        if self.handler is None:
            raise NotImplementedError(f"Handler not implemented for tool: {self.name}")
        return await self.handler(**arguments)


# =============================================================================
# Tool Implementations
# =============================================================================


def _result_json(result: ToolResult) -> str:
    """Serialize a structured tool result for MCP text content."""
    return json.dumps(result.to_dict(), indent=2)


def _error_result(code: str, message: str, stage: str, path: str | None = None) -> str:
    return _result_json(
        ToolResult(
            ok=False,
            summary=message,
            errors=[
                Diagnostic(
                    severity="error",
                    code=code,
                    message=message,
                    location={"path": path} if path is not None else None,
                    stage=stage,
                )
            ],
        )
    )


async def search_kicad_parts(query: str, limit: int = 10) -> str:
    """Search KiCad component libraries."""
    from circuitweaver.library import search_parts

    if limit < 1:
        return _error_result(
            "invalid_limit",
            "limit must be a positive integer.",
            "search_kicad_parts",
        )

    results = search_parts(query, limit=limit)
    parts = [
        {
            "library_id": part.library_id,
            "library_name": part.library_name,
            "symbol_name": part.symbol_name,
            "description": part.description,
            "keywords": part.keywords,
            "footprint": part.default_footprint,
            "datasheet": part.datasheet,
        }
        for part in results
    ]
    summary = (
        f"Found {len(parts)} result(s) for '{query}'."
        if parts
        else f"No results found for '{query}'."
    )
    return _result_json(ToolResult(ok=True, summary=summary, data={"parts": parts}))


async def get_symbol_pins(symbol_id: str) -> str:
    """Get pin information for a KiCad symbol.

    Use this to look up pin numbers and names before creating source_port elements.
    """
    from circuitweaver.library import get_symbol_info
    from circuitweaver.types.errors import LibraryNotFoundError, SymbolNotFoundError

    try:
        pins = get_symbol_info(symbol_id).pins
    except (ValueError, SymbolNotFoundError, LibraryNotFoundError) as e:
        return _result_json(
            ToolResult(
                ok=False,
                summary=f"Could not load pins for {symbol_id}: {e}",
                errors=[
                    Diagnostic(
                        severity="error",
                        code="symbol_lookup_failed",
                        message=str(e),
                        stage="get_symbol_pins",
                    )
                ],
                data={"pins": []},
            )
        )

    pin_records = []
    for pin in pins:
        grid_offset = pin.grid_offset
        pin_records.append(
            {
                "number": str(pin.number),
                "name": pin.name,
                "electrical_type": pin.electrical_type,
                "direction": pin.direction,
                "grid_offset": (
                    {"x": grid_offset.x, "y": grid_offset.y}
                    if grid_offset is not None
                    else None
                ),
            }
        )

    return _result_json(
        ToolResult(
            ok=True,
            summary=f"Found {len(pin_records)} pin(s) for {symbol_id}.",
            data={"pins": pin_records},
        )
    )


async def validate_circuit_json(file_path: str) -> str:
    """Validate a Circuit JSON file (source_* elements only)."""
    from circuitweaver.validator import validate_circuit_file as _validate

    path = Path(file_path)

    # Basic path validation - resolve to absolute and check it exists
    try:
        resolved_path = path.resolve(strict=False)
    except (OSError, ValueError) as e:
        return _error_result("invalid_path", f"Invalid path: {e}", "validate", file_path)

    if not resolved_path.exists():
        return _error_result("file_not_found", f"File not found: {file_path}", "validate", file_path)

    if not resolved_path.is_file():
        return _error_result("not_a_file", f"Not a file: {file_path}", "validate", file_path)

    result = _validate(resolved_path)
    errors = [
        Diagnostic(
            severity="error",
            code=error.rule,
            message=error.message,
            element_id=error.element_id,
            location=error.location,
            stage="validate",
        )
        for error in result.errors
    ]
    warnings = [
        Diagnostic(
            severity="warning",
            code=warning.rule,
            message=warning.message,
            element_id=warning.element_id,
            location=warning.location,
            stage="validate",
        )
        for warning in result.warnings
    ]
    summary = (
        f"{file_path} is valid."
        if result.is_valid
        else f"{file_path} has {len(result.errors)} validation error(s)."
    )
    return _result_json(
        ToolResult(
            ok=result.is_valid,
            summary=summary,
            errors=errors,
            warnings=warnings,
            data={"validation": result.to_dict()},
        )
    )


async def create_schematic(
    file_path: str,
    output_dir: str | None = None,
    project_name: str | None = None,
    write_schematic_json: bool = True,
    write_kicad: bool = True,
    write_debug_layout: bool = False,
    debug: bool = False,
) -> str:
    """Run auto-layout on a Circuit JSON file to generate schematic elements."""
    from circuitweaver.compiler.engine import CompileEngine
    from circuitweaver.io.json import read_circuit, write_schematic

    path = Path(file_path)
    if not path.exists():
        return _error_result("file_not_found", f"File not found: {file_path}", "create_schematic", file_path)
    if not path.is_file():
        return _error_result("not_a_file", f"Not a file: {file_path}", "create_schematic", file_path)

    try:
        elements = read_circuit(path)
        engine = CompileEngine()
        resolved_output_dir = Path(output_dir) if output_dir else path.parent
        resolved_output_dir.mkdir(parents=True, exist_ok=True)
        name = project_name or path.stem
        should_write_debug = write_debug_layout or debug

        # Run layout with optional debug info
        debug_dir = resolved_output_dir if should_write_debug else None
        debug_basename = name if should_write_debug else None

        updated_elements = engine.layout(
            elements, debug_dir=debug_dir, debug_basename=debug_basename
        )
        outputs: list[OutputArtifact] = []

        if write_schematic_json:
            schematic_path = resolved_output_dir / f"{name}_schematic.json"
            write_schematic(schematic_path, updated_elements)
            outputs.append(
                OutputArtifact(
                    kind="schematic_json",
                    path=schematic_path,
                    name=schematic_path.name,
                    metadata={"element_count": len(updated_elements)},
                )
            )

        if write_kicad:
            root_schematic = engine.compile(updated_elements, resolved_output_dir, project_name=name)
            outputs.append(
                OutputArtifact(
                    kind="kicad_schematic",
                    path=root_schematic,
                    name=root_schematic.name,
                )
            )
            project_file = resolved_output_dir / f"{name}.kicad_pro"
            if project_file.exists():
                outputs.append(
                    OutputArtifact(kind="kicad_project", path=project_file, name=project_file.name)
                )

        if should_write_debug:
            for suffix in ("layout_in", "layout_out"):
                debug_path = resolved_output_dir / f"{name}_{suffix}.json"
                if debug_path.exists():
                    outputs.append(
                        OutputArtifact(kind=f"debug_{suffix}", path=debug_path, name=debug_path.name)
                    )

        return _result_json(
            ToolResult(
                ok=True,
                summary=f"Generated {len(outputs)} output file(s) in {resolved_output_dir}.",
                outputs=outputs,
                data={
                    "artifacts": [artifact.to_dict() for artifact in outputs],
                    "output_dir": str(resolved_output_dir),
                    "project_name": name,
                },
            )
        )
    except Exception as e:
        return _error_result("create_schematic_failed", str(e), "create_schematic", file_path)


async def run_erc(
    file_path: str,
    output_dir: str | None = None,
    project_name: str | None = None,
    keep_generated: bool = False,
) -> str:
    """Run Electrical Rules Check (ERC) on a Circuit JSON file."""
    try:
        result = run_erc_for_path(
            Path(file_path),
            output_dir=Path(output_dir) if output_dir else None,
            project_name=project_name,
            keep_generated=keep_generated,
        )
        if "erc" not in result.data:
            result.data["erc"] = {
                "is_valid": result.ok,
                "errors": [error.message for error in result.errors],
                "warnings": [warning.message for warning in result.warnings],
            }
        return _result_json(result)
    except Exception as e:
        return _error_result("erc_failed", str(e), "erc", file_path)


# =============================================================================
# Tool Registry
# =============================================================================

TOOL_REGISTRY: dict[str, ToolHandler] = {
    "search_kicad_parts": ToolHandler(
        name="search_kicad_parts",
        description="Search KiCad component libraries by keyword. Returns library IDs, descriptions, and default footprints.",
        parameters=[
            ToolParameter(
                name="query",
                type="string",
                description=(
                    "case-insensitive search query matched against library IDs, names, "
                    "descriptions, and keywords (e.g., 'STM32G4', 'resistor 0603')."
                ),
            ),
            ToolParameter(
                name="limit",
                type="integer",
                description="positive maximum number of results to return.",
                required=False,
                default=10,
            ),
        ],
        handler=search_kicad_parts,
    ),
    "get_symbol_pins": ToolHandler(
        name="get_symbol_pins",
        description="Get pin information for a KiCad symbol. Use this to look up pin numbers and names before creating source_port elements.",
        parameters=[
            ToolParameter(
                name="symbol_id",
                type="string",
                description="Symbol ID (e.g., 'Device:R', 'MCU_ST_STM32G4:STM32G431CBUx')",
            ),
        ],
        handler=get_symbol_pins,
    ),
    "validate_circuit_json": ToolHandler(
        name="validate_circuit_json",
        description="Validate a Circuit JSON file containing source_* elements. Checks for valid IDs, references, and trace connections.",
        parameters=[
            ToolParameter(
                name="file_path",
                type="string",
                description="Path to the input Circuit JSON file.",
            ),
        ],
        handler=validate_circuit_json,
    ),
    "create_schematic": ToolHandler(
        name="create_schematic",
        description="Run auto-layout on a Circuit JSON file to generate schematic elements. Positions components and routes traces.",
        parameters=[
            ToolParameter(
                name="file_path",
                type="string",
                description="Path to the input Circuit JSON file.",
            ),
            ToolParameter(
                name="output_dir",
                type="string",
                description=(
                    "Optional output directory. Defaults to the input file directory when omitted."
                ),
                required=False,
            ),
            ToolParameter(
                name="project_name",
                type="string",
                description="Optional KiCad project/output basename. Defaults to the input file stem.",
                required=False,
            ),
            ToolParameter(
                name="write_schematic_json",
                type="boolean",
                description="Write the generated Circuit JSON schematic file.",
                required=False,
                default=True,
            ),
            ToolParameter(
                name="write_kicad",
                type="boolean",
                description="Write KiCad .kicad_sch and .kicad_pro files.",
                required=False,
                default=True,
            ),
            ToolParameter(
                name="write_debug_layout",
                type="boolean",
                description="Write intermediate ELK layout input/output debug files.",
                required=False,
                default=False,
            ),
            ToolParameter(
                name="debug",
                type="boolean",
                description=(
                    "Deprecated alias for write_debug_layout. If true, writes intermediate "
                    "ELK layout data files."
                ),
                required=False,
                default=False,
            ),
        ],
        handler=create_schematic,
    ),
    "run_erc": ToolHandler(
        name="run_erc",
        description="Compile a Circuit JSON file in a temporary directory and run KiCad Electrical Rules Check (ERC) on the generated schematic.",
        parameters=[
            ToolParameter(
                name="file_path",
                type="string",
                description="Path to a Circuit JSON file or existing .kicad_sch schematic.",
            ),
            ToolParameter(
                name="output_dir",
                type="string",
                description="Optional output directory for generated files when file_path is Circuit JSON.",
                required=False,
            ),
            ToolParameter(
                name="project_name",
                type="string",
                description="Optional KiCad project name when compiling Circuit JSON before ERC.",
                required=False,
            ),
            ToolParameter(
                name="keep_generated",
                type="boolean",
                description="Keep generated ERC input artifacts when possible.",
                required=False,
                default=False,
            ),
        ],
        handler=run_erc,
    ),
}

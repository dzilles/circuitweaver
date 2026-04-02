"""Tool registry for CircuitWeaver MCP server.

This module defines the registry of all available tools and their handlers.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from mcp.types import Tool


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


async def search_kicad_parts(query: str, limit: int = 10) -> str:
    """Search KiCad component libraries."""
    from circuitweaver.library import search_parts

    results = search_parts(query, limit=limit)
    if not results:
        return f"No results found for '{query}'"

    lines = [f"Found {len(results)} results for '{query}':\n"]
    for part in results:
        lines.append(f"- {part.library_id}")
        if part.description:
            lines.append(f"  Description: {part.description}")
        if part.default_footprint:
            lines.append(f"  Footprint: {part.default_footprint}")
        lines.append("")

    return "\n".join(lines)


async def get_symbol_pins(symbol_id: str) -> str:
    """Get pin information for a KiCad symbol.

    Use this to look up pin numbers and names before creating source_port elements.
    """
    from circuitweaver.library import get_symbol_pinout as _get_pinout

    try:
        pins = _get_pinout(symbol_id)
    except ValueError as e:
        return f"Error: {e}"

    if not pins:
        return f"No pins found for {symbol_id}"

    # Calculate column widths for a pretty Markdown table
    col1_w = max(len("Pin #"), max((len(str(p.number)) for p in pins), default=0))
    col2_w = max(len("Name"), max((len(p.name) for p in pins), default=0))
    col3_w = max(len("Electrical Type"), max((len(p.electrical_type) for p in pins), default=0))

    header = f"| {'Pin #'.ljust(col1_w)} | {'Name'.ljust(col2_w)} | {'Electrical Type'.ljust(col3_w)} |"
    sep = f"| {'-' * col1_w} | {'-' * col2_w} | {'-' * col3_w} |"
    
    lines = [f"Pins for {symbol_id}:\n", header, sep]

    for pin in pins:
        lines.append(
            f"| {str(pin.number).ljust(col1_w)} | {pin.name.ljust(col2_w)} | {pin.electrical_type.ljust(col3_w)} |"
        )

    return "\n".join(lines)


async def validate_circuit_json(file_path: str) -> str:
    """Validate a Circuit JSON file (source_* elements only)."""
    from pathlib import Path

    from circuitweaver.validator import validate_circuit_file as _validate

    path = Path(file_path)
    if not path.exists():
        return f"Error: File not found: {file_path}"

    result = _validate(path)

    if result.is_valid:
        msg = f"SUCCESS: {file_path} is valid"
        if result.warnings:
            msg += f"\n\nWarnings ({len(result.warnings)}):"
            for w in result.warnings:
                msg += f"\n- {w}"
        return msg
    else:
        msg = f"FAILED: {file_path} has {len(result.errors)} error(s)"
        for e in result.errors:
            msg += f"\n- {e}"
        if result.warnings:
            msg += f"\n\nWarnings ({len(result.warnings)}):"
            for w in result.warnings:
                msg += f"\n- {w}"
        return msg


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
                description="Search query (e.g., 'STM32G4', 'resistor 0603')",
            ),
            ToolParameter(
                name="limit",
                type="integer",
                description="Maximum number of results",
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
                description="Path to the Circuit JSON file",
            ),
        ],
        handler=validate_circuit_json,
    ),
}

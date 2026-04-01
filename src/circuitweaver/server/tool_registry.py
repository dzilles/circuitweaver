"""Tool registry for CircuitWeaver MCP server.

This module defines the registry of all available tools and their handlers.
"""

from abc import ABC, abstractmethod
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


async def get_symbol_pinout(symbol_id: str) -> str:
    """Get pinout information for a KiCad symbol."""
    from circuitweaver.library import get_symbol_pinout as _get_pinout

    try:
        pins = _get_pinout(symbol_id)
    except ValueError as e:
        return f"Error: {e}"

    lines = [f"Pinout for {symbol_id}:\n"]
    lines.append("Pin | Name | X | Y | Direction | Type")
    lines.append("----|------|---|---|-----------|-----")

    for pin in pins:
        lines.append(
            f"{pin.number} | {pin.name} | {pin.grid_offset.x} | "
            f"{pin.grid_offset.y} | {pin.direction} | {pin.electrical_type}"
        )

    return "\n".join(lines)


async def validate_circuit_file(file_path: str) -> str:
    """Validate a Circuit JSON file."""
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


async def compile_to_kicad(input_file: str, output_dir: str) -> str:
    """Compile Circuit JSON to KiCad schematic."""
    from pathlib import Path

    from circuitweaver.compiler import compile_to_kicad as _compile
    from circuitweaver.validator import validate_circuit_file

    input_path = Path(input_file)
    output_path = Path(output_dir)

    if not input_path.exists():
        return f"Error: File not found: {input_file}"

    # Validate first
    result = validate_circuit_file(input_path)
    if not result.is_valid:
        return f"Validation failed. Fix errors before compiling:\n" + "\n".join(
            f"- {e}" for e in result.errors
        )

    try:
        output_path.mkdir(parents=True, exist_ok=True)
        output_files = _compile(input_path, output_path)
        return f"SUCCESS: Compiled to:\n" + "\n".join(f"- {f}" for f in output_files)
    except Exception as e:
        return f"Compilation failed: {e}"


async def run_erc(schematic_file: str) -> str:
    """Run Electrical Rules Check on a KiCad schematic."""
    from pathlib import Path

    from circuitweaver.erc import run_erc as _run_erc

    path = Path(schematic_file)
    if not path.exists():
        return f"Error: File not found: {schematic_file}"

    result = _run_erc(path)

    if result.passed:
        msg = f"ERC PASSED: {schematic_file}"
        if result.warnings:
            msg += f"\n\nWarnings ({len(result.warnings)}):"
            for w in result.warnings:
                msg += f"\n- {w}"
        return msg
    else:
        msg = f"ERC FAILED: {schematic_file}"
        msg += f"\n\nErrors ({len(result.errors)}):"
        for e in result.errors:
            msg += f"\n- {e}"
        if result.warnings:
            msg += f"\n\nWarnings ({len(result.warnings)}):"
            for w in result.warnings:
                msg += f"\n- {w}"
        return msg


async def read_file(file_path: str) -> str:
    """Read contents of a file."""
    from pathlib import Path

    path = Path(file_path)
    if not path.exists():
        return f"Error: File not found: {file_path}"

    try:
        content = path.read_text()
        return content
    except Exception as e:
        return f"Error reading file: {e}"


async def write_file(file_path: str, content: str) -> str:
    """Write content to a file."""
    from pathlib import Path

    path = Path(file_path)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return f"Successfully wrote {len(content)} characters to {file_path}"
    except Exception as e:
        return f"Error writing file: {e}"


async def edit_file(file_path: str, old_text: str, new_text: str) -> str:
    """Edit a file by replacing text."""
    from pathlib import Path

    path = Path(file_path)
    if not path.exists():
        return f"Error: File not found: {file_path}"

    try:
        content = path.read_text()
        if old_text not in content:
            return f"Error: Text to replace not found in {file_path}"

        count = content.count(old_text)
        if count > 1:
            return f"Error: Text to replace appears {count} times. Make it more specific."

        new_content = content.replace(old_text, new_text)
        path.write_text(new_content)
        return f"Successfully edited {file_path}"
    except Exception as e:
        return f"Error editing file: {e}"


async def get_symbol_info(symbol_id: str) -> str:
    """Get complete information about a KiCad symbol."""
    from circuitweaver.library import get_symbol_info as _get_info

    try:
        info = _get_info(symbol_id)
    except ValueError as e:
        return f"Error: {e}"

    lines = [f"Symbol Info for {symbol_id}:\n"]
    lines.append(f"Description: {info.description}")
    lines.append(f"Keywords: {info.keywords}")
    lines.append(f"Size: {info.width} x {info.height} grid units")
    lines.append(f"Bounding Box: ({info.bounding_box_min.x}, {info.bounding_box_min.y}) to ({info.bounding_box_max.x}, {info.bounding_box_max.y})\n")
    
    lines.append("Pins:")
    lines.append("Pin | Name | X | Y | Direction | Type")
    lines.append("----|------|---|---|-----------|-----")

    for pin in info.pins:
        lines.append(
            f"{pin.number} | {pin.name} | {pin.grid_offset.x} | "
            f"{pin.grid_offset.y} | {pin.direction} | {pin.electrical_type}"
        )

    return "\n".join(lines)


async def get_format_examples(category: str = "all") -> str:
    """Get examples of valid Circuit JSON formatting and Library:Symbol usage."""
    examples = {
        "symbols": """
### Library:Symbol Examples
When defining components, use the full 'Library:Symbol' ID for better reliability:
- MCU: `MCU_ST_STM32G4:STM32G431CBUx`
- Resistor: `Device:R`
- Capacitor: `Device:C`
- LDO: `Regulator_Linear:AMS1117-3.3`
- Buck: `Regulator_Switching:TPS5420D`
- Connector: `Connector_AMASS:AMASS_XT30U-F_1x02_P5.0mm_Vertical`
""",
        "circuit": """
### Minimal Circuit JSON
[
  {
    "type": "source_component",
    "source_component_id": "comp_r1",
    "name": "R1",
    "value": "10k",
    "footprint": "Resistor_SMD:R_0603_1608Metric"
  },
  {
    "type": "schematic_component",
    "schematic_component_id": "sch_r1",
    "source_component_id": "comp_r1",
    "center": { "x": 100, "y": 100 },
    "rotation": 0
  }
]
"""
    }
    
    if category == "symbols":
        return examples["symbols"]
    if category == "circuit":
        return examples["circuit"]
        
    return examples["symbols"] + "\n" + examples["circuit"]


# =============================================================================
# Tool Registry
# =============================================================================

TOOL_REGISTRY: dict[str, ToolHandler] = {
    "get_format_examples": ToolHandler(
        name="get_format_examples",
        description="Get examples of valid Circuit JSON formatting and correct Library:Symbol identifiers for common parts.",
        parameters=[
            ToolParameter(
                name="category",
                type="string",
                description="Category of examples ('symbols', 'circuit', or 'all')",
                required=False,
                default="all",
            ),
        ],
        handler=get_format_examples,
    ),
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
    "get_symbol_info": ToolHandler(
        name="get_symbol_info",
        description="Get complete information about a KiCad symbol including size (bounding box), pins, and description. Essential for calculating placement to avoid overlaps.",
        parameters=[
            ToolParameter(
                name="symbol_id",
                type="string",
                description="Symbol ID (e.g., 'Device:R', 'MCU_ST_STM32G4:STM32G431CBUx')",
            ),
        ],
        handler=get_symbol_info,
    ),
    "get_symbol_pinout": ToolHandler(
        name="get_symbol_pinout",
        description="Get pin positions for a KiCad symbol in grid units. Essential for routing orthogonal traces.",
        parameters=[
            ToolParameter(
                name="symbol_id",
                type="string",
                description="Symbol ID (e.g., 'Device:R', 'MCU_ST_STM32G4:STM32G431CBUx')",
            ),
        ],
        handler=get_symbol_pinout,
    ),
    "validate_circuit_file": ToolHandler(
        name="validate_circuit_file",
        description="Validate a Circuit JSON file for errors (coordinates, orthogonal traces, source-first rule, etc.)",
        parameters=[
            ToolParameter(
                name="file_path",
                type="string",
                description="Path to the Circuit JSON file",
            ),
        ],
        handler=validate_circuit_file,
    ),
    "compile_to_kicad": ToolHandler(
        name="compile_to_kicad",
        description="Compile Circuit JSON to KiCad .kicad_sch files. Requires KiCad 10.0+ installed.",
        parameters=[
            ToolParameter(
                name="input_file",
                type="string",
                description="Path to the Circuit JSON file",
            ),
            ToolParameter(
                name="output_dir",
                type="string",
                description="Directory to write output files",
            ),
        ],
        handler=compile_to_kicad,
    ),
    "run_erc": ToolHandler(
        name="run_erc",
        description="Run Electrical Rules Check on a KiCad schematic using kicad-cli. Requires KiCad 10.0+ installed.",
        parameters=[
            ToolParameter(
                name="schematic_file",
                type="string",
                description="Path to the .kicad_sch file",
            ),
        ],
        handler=run_erc,
    ),
    "read_file": ToolHandler(
        name="read_file",
        description="Read the contents of a file.",
        parameters=[
            ToolParameter(
                name="file_path",
                type="string",
                description="Path to the file to read",
            ),
        ],
        handler=read_file,
    ),
    "write_file": ToolHandler(
        name="write_file",
        description="Write content to a file, creating directories as needed.",
        parameters=[
            ToolParameter(
                name="file_path",
                type="string",
                description="Path to the file to write",
            ),
            ToolParameter(
                name="content",
                type="string",
                description="Content to write to the file",
            ),
        ],
        handler=write_file,
    ),
    "edit_file": ToolHandler(
        name="edit_file",
        description="Edit a file by replacing specific text. The old_text must appear exactly once.",
        parameters=[
            ToolParameter(
                name="file_path",
                type="string",
                description="Path to the file to edit",
            ),
            ToolParameter(
                name="old_text",
                type="string",
                description="Text to replace (must be unique in file)",
            ),
            ToolParameter(
                name="new_text",
                type="string",
                description="Replacement text",
            ),
        ],
        handler=edit_file,
    ),
}

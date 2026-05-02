"""MCP Server implementation for CircuitWeaver.

This module provides the main MCP server that exposes CircuitWeaver's
tools to AI assistants like Claude and Gemini.
"""

import asyncio
import logging
from collections.abc import Sequence
from importlib import resources
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import GetPromptResult, Prompt, PromptMessage, Resource, TextContent, Tool

from circuitweaver.server.tool_registry import TOOL_REGISTRY, ToolHandler

logger = logging.getLogger(__name__)


def create_server(
    enabled_tools: Sequence[str] | None = None,
) -> Server:
    """Create and configure the MCP server.

    Args:
        enabled_tools: List of tool names to enable. If None, all tools are enabled.

    Returns:
        Configured MCP Server instance.
    """
    server = Server("circuitweaver")

    if enabled_tools:
        unknown_tools = sorted(set(enabled_tools) - set(TOOL_REGISTRY))
        if unknown_tools:
            raise ValueError(f"Unknown MCP tool(s): {', '.join(unknown_tools)}")
        tools = {
            name: handler
            for name, handler in TOOL_REGISTRY.items()
            if name in enabled_tools
        }
    else:
        tools = TOOL_REGISTRY

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List all available tools."""
        return [handler.to_mcp_tool() for handler in tools.values()]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle tool calls."""
        if name not in tools:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

        handler = tools[name]
        try:
            result = await handler.execute(arguments)
            return [TextContent(type="text", text=result)]
        except Exception as e:
            logger.exception(f"Error executing tool {name}")
            return [TextContent(type="text", text=f"Error: {e}")]

    @server.list_resources()
    async def list_resources() -> list[Resource]:
        """List available resources (documentation, examples)."""
        return [
            Resource(
                uri="circuitweaver://docs/readme",
                name="CircuitWeaver README",
                description="Project overview, installation instructions, and quick-start examples.",
                mimeType="text/markdown",
            ),
            Resource(
                uri="circuitweaver://docs/install",
                name="Installation Guide",
                description="Linux, Windows, and optional HTTP installation instructions.",
                mimeType="text/markdown",
            ),
            Resource(
                uri="circuitweaver://docs/mcp-workflow",
                name="MCP Workflow Guide",
                description="Recommended workflow for using CircuitWeaver through MCP clients.",
                mimeType="text/markdown",
            ),
            Resource(
                uri="circuitweaver://tools/reference",
                name="Tool Reference",
                description="Live reference generated from the MCP tool registry.",
                mimeType="text/markdown",
            ),
            Resource(
                uri="circuitweaver://docs/circuit-json-spec",
                name="Circuit JSON Specification",
                description="Complete specification for the Circuit JSON format",
                mimeType="text/markdown",
            ),
            Resource(
                uri="circuitweaver://docs/troubleshooting",
                name="Troubleshooting Guide",
                description="Common installation and runtime issues.",
                mimeType="text/markdown",
            ),
            Resource(
                uri="circuitweaver://examples/simple-led",
                name="Simple LED Example",
                description="A complete logic-only Circuit JSON example.",
                mimeType="text/markdown",
            ),
            Resource(
                uri="circuitweaver://docs/examples",
                name="Example Circuits",
                description="Alias for circuitweaver://examples/simple-led.",
                mimeType="text/markdown",
            ),
        ]

    @server.read_resource()
    async def read_resource(uri: str) -> str:
        """Read resource content."""
        uri = str(uri)
        if uri == "circuitweaver://docs/readme":
            return _get_readme()
        elif uri == "circuitweaver://docs/install":
            return _get_install_guide()
        elif uri == "circuitweaver://docs/mcp-workflow":
            return _get_mcp_workflow()
        elif uri == "circuitweaver://tools/reference":
            return _get_tools_reference(tools)
        elif uri == "circuitweaver://docs/circuit-json-spec":
            return _get_circuit_json_spec()
        elif uri == "circuitweaver://docs/troubleshooting":
            return _get_troubleshooting()
        elif uri in {
            "circuitweaver://examples/simple-led",
            "circuitweaver://docs/examples",
        }:
            return _get_examples()
        else:
            raise ValueError(f"Unknown resource: {uri}")

    @server.list_prompts()
    async def list_prompts() -> list[Prompt]:
        """List available prompts."""
        return [
            Prompt(
                name="design-guidelines",
                description="Workflow guidance for designing Circuit JSON schematics with CircuitWeaver.",
            )
        ]

    @server.get_prompt()
    async def get_prompt(name: str, _arguments: dict[str, str] | None) -> GetPromptResult:
        """Get a specific prompt."""
        if name != "design-guidelines":
            raise ValueError(f"Unknown prompt: {name}")

        return GetPromptResult(
            description="System instructions for CircuitWeaver",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=(
                            "You are helping design electronic schematics with CircuitWeaver.\n\n"
                            "Before generating or modifying Circuit JSON, load these MCP resources "
                            "when available:\n"
                            "- circuitweaver://docs/mcp-workflow\n"
                            "- circuitweaver://tools/reference\n"
                            "- circuitweaver://docs/circuit-json-spec\n"
                            "- circuitweaver://examples/simple-led when an example is useful\n\n"
                            "Use the MCP client's normal file tools to create or edit JSON files. "
                            "Use CircuitWeaver MCP tools only for CircuitWeaver-specific actions: "
                            "part lookup, pin lookup, validation, schematic generation, and ERC. "
                            "Do not call tools that are not listed in circuitweaver://tools/reference."
                        ),
                    ),
                )
            ],
        )

    return server


def _read_packaged_or_source_text(package_path: str, source_path: str) -> str | None:
    """Read a text file from an installed package, falling back to the source tree."""
    try:
        return resources.files("circuitweaver").joinpath(package_path).read_text()
    except (FileNotFoundError, ModuleNotFoundError):
        pass

    from pathlib import Path

    path = Path(__file__).parent.parent.parent.parent / source_path
    if path.exists():
        return path.read_text()

    return None


def _get_readme() -> str:
    """Get the project README."""
    content = _read_packaged_or_source_text("README.md", "README.md")
    if content is not None:
        return content

    return "# CircuitWeaver README\n\nError: README file not found on server."


def _get_install_guide() -> str:
    """Get installation instructions extracted from the README."""
    readme = _get_readme()
    start = readme.find("## Installation")
    end = readme.find("## Quick Start")
    if start != -1 and end != -1 and end > start:
        return readme[start:end].strip()

    return "# Installation Guide\n\nError: Installation section not found in README."


def _get_mcp_workflow() -> str:
    """Get the MCP workflow guide."""
    content = _read_packaged_or_source_text("docs/mcp-workflow.md", "docs/mcp-workflow.md")
    if content is not None:
        return content

    return "# MCP Workflow Guide\n\nError: MCP workflow guide not found on server."


def _get_tools_reference(tools: dict[str, ToolHandler]) -> str:
    """Generate a tool reference from the active tool registry."""
    lines = [
        "# CircuitWeaver MCP Tool Reference",
        "",
        "This reference is generated from the currently enabled MCP tools.",
        "",
    ]

    for tool in tools.values():
        lines.append(f"## `{tool.name}`")
        lines.append("")
        lines.append(tool.description)
        lines.append("")
        if tool.parameters:
            lines.append("| Parameter | Type | Required | Default | Description |")
            lines.append("|-----------|------|----------|---------|-------------|")
            for param in tool.parameters:
                required = "yes" if param.required else "no"
                default = "" if param.default is None else f"`{param.default}`"
                lines.append(
                    f"| `{param.name}` | `{param.type}` | {required} | {default} | "
                    f"{param.description} |"
                )
            lines.append("")
        else:
            lines.append("No parameters.")
            lines.append("")

    return "\n".join(lines)


def _get_troubleshooting() -> str:
    """Get troubleshooting instructions."""
    content = _read_packaged_or_source_text("docs/troubleshooting.md", "docs/troubleshooting.md")
    if content is not None:
        return content

    return "# Troubleshooting Guide\n\nError: Troubleshooting guide not found on server."


def run_server(
    server: Server,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 3000,
) -> None:
    """Run the MCP server with the specified transport.

    Args:
        server: The MCP server instance to run.
        transport: Transport type ('stdio' or 'http').
        host: Host for HTTP transport.
        port: Port for HTTP transport.
    """
    if transport == "stdio":
        asyncio.run(_run_stdio(server))
    elif transport == "http":
        _run_http(server, host, port)
    else:
        raise ValueError(f"Unknown transport: {transport}")


async def _run_stdio(server: Server) -> None:
    """Run server with stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def _run_http(server: Server, host: str, port: int) -> None:
    """Run server with HTTP transport."""
    try:
        import uvicorn

        from circuitweaver.server.http_transport import create_http_app
    except ImportError:
        raise ImportError(
            "HTTP transport requires additional dependencies. "
            "Install with: pip install circuitweaver[http]"
        ) from None

    app = create_http_app(server)
    uvicorn.run(app, host=host, port=port)


def _get_circuit_json_spec() -> str:
    """Get the Circuit JSON specification document."""
    content = _read_packaged_or_source_text(
        "docs/circuit-json-spec.md",
        "docs/circuit-json-spec.md",
    )
    if content is not None:
        return content

    return "# Circuit JSON Specification\n\nError: Documentation file not found on server."


def _get_examples() -> str:
    """Get example circuits."""
    example = _read_packaged_or_source_text(
        "examples/simple_led/circuit.json",
        "examples/simple_led/circuit.json",
    )
    if example is not None:
        return f"# Simple LED Example\n\n```json\n{example}\n```"

    return "# Example Circuits\n\nError: Example files not found on server."

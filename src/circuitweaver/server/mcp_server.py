"""MCP Server implementation for CircuitWeaver.

This module provides the main MCP server that exposes CircuitWeaver's
tools to AI assistants like Claude and Gemini.
"""

import asyncio
import logging
from typing import Any, Optional, Sequence

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, TextContent, Tool

from circuitweaver.server.tool_registry import TOOL_REGISTRY, ToolHandler
from circuitweaver import __version__

logger = logging.getLogger(__name__)


def create_server(
    enabled_tools: Optional[Sequence[str]] = None,
) -> Server:
    """Create and configure the MCP server.

    Args:
        enabled_tools: List of tool names to enable. If None, all tools are enabled.

    Returns:
        Configured MCP Server instance.
    """
    server = Server("circuitweaver")

    # Filter tools if specific ones are requested
    if enabled_tools:
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
                uri="circuitweaver://docs/circuit-json-spec",
                name="Circuit JSON Specification",
                description="Complete specification for the Circuit JSON format",
                mimeType="text/markdown",
            ),
            Resource(
                uri="circuitweaver://docs/examples",
                name="Example Circuits",
                description="Example Circuit JSON files",
                mimeType="text/markdown",
            ),
        ]

    @server.read_resource()
    async def read_resource(uri: str) -> str:
        """Read resource content."""
        if uri == "circuitweaver://docs/circuit-json-spec":
            return _get_circuit_json_spec()
        elif uri == "circuitweaver://docs/examples":
            return _get_examples()
        else:
            raise ValueError(f"Unknown resource: {uri}")

    from mcp.types import Prompt, GetPromptResult, PromptMessage

    @server.list_prompts()
    async def list_prompts() -> list[Prompt]:
        """List available prompts."""
        return [
            Prompt(
                name="design-guidelines",
                description="System instructions and rules for generating valid Circuit JSON schematics.",
            )
        ]

    @server.get_prompt()
    async def get_prompt(name: str, arguments: dict[str, str] | None) -> GetPromptResult:
        """Get a specific prompt."""
        if name != "design-guidelines":
            raise ValueError(f"Unknown prompt: {name}")

        spec = _get_circuit_json_spec()
        return GetPromptResult(
            description="System instructions for CircuitWeaver",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=f"You are a specialized CircuitWeaver agent. Follow these rules exactly when generating JSON:\n\n{spec}",
                    ),
                )
            ],
        )

    return server


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
        from circuitweaver.server.http_transport import create_http_app
        import uvicorn
    except ImportError:
        raise ImportError(
            "HTTP transport requires additional dependencies. "
            "Install with: pip install circuitweaver[http]"
        )

    app = create_http_app(server)
    uvicorn.run(app, host=host, port=port)


def _get_circuit_json_spec() -> str:
    """Get the Circuit JSON specification document."""
    from pathlib import Path
    
    # Try to find the file relative to this script
    path = Path(__file__).parent.parent.parent.parent / "docs" / "circuit-json-spec.md"
    if path.exists():
        return path.read_text()
        
    return "# Circuit JSON Specification\n\nError: Documentation file not found on server."


def _get_examples() -> str:
    """Get example circuits."""
    from pathlib import Path
    
    # Try to find the example file
    path = Path(__file__).parent.parent.parent.parent / "examples" / "simple_led" / "circuit.json"
    if path.exists():
        return f"# Simple LED Example\n\n```json\n{path.read_text()}\n```"
        
    return "# Example Circuits\n\nError: Example files not found on server."

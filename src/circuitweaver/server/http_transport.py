"""HTTP transport for CircuitWeaver MCP server.

This module provides HTTP/SSE transport for the MCP server,
allowing remote connections from Claude CLI and other tools.

Requires the [http] extra: pip install circuitweaver[http]
"""

from typing import Any

try:
    from fastapi import FastAPI, Request, Response
except ImportError:
    raise ImportError(
        "HTTP transport requires additional dependencies. "
        "Install with: pip install circuitweaver[http]"
    ) from None

from mcp.server import Server
from mcp.types import (
    CallToolRequest,
    CallToolRequestParams,
    ListResourcesRequest,
    ListToolsRequest,
    ReadResourceRequest,
    ReadResourceRequestParams,
)


def create_http_app(server: Server) -> FastAPI:
    """Create a FastAPI app wrapping the MCP server.

    Args:
        server: The MCP server instance.

    Returns:
        FastAPI application.
    """
    app = FastAPI(
        title="CircuitWeaver MCP Server",
        description="MCP server for generating KiCad schematics from Circuit JSON",
        version="0.1.0",
    )

    @app.get("/")
    async def root() -> dict[str, str]:
        """Health check endpoint."""
        return {
            "name": "CircuitWeaver",
            "status": "running",
            "protocol": "MCP",
        }

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy"}

    @app.post("/mcp")
    async def mcp_endpoint(request: Request) -> Response:
        """Main MCP endpoint for JSON-RPC requests.

        This endpoint handles MCP protocol messages over HTTP.
        """
        body = await request.json()

        # Process the MCP request
        # This is a simplified implementation - full implementation
        # would properly handle the MCP protocol over HTTP
        response = await _handle_mcp_request(server, body)

        return Response(
            content=response,
            media_type="application/json",
        )

    return app


async def _handle_mcp_request(server: Server, body: dict[str, Any]) -> str:
    """Handle an MCP JSON-RPC request.

    Args:
        server: The MCP server instance.
        body: The JSON-RPC request body.

    Returns:
        JSON-RPC response as string.
    """
    import json

    # This is a simplified implementation
    # Full implementation would properly route to MCP handlers

    method = body.get("method", "")
    params = body.get("params", {})
    request_id = body.get("id")

    try:
        if method == "tools/list":
            # List available tools
            req = ListToolsRequest(method="tools/list")
            response = await server.request_handlers[ListToolsRequest](req)
            tools = response.root.tools
            result = {"tools": [t.model_dump(mode="json") for t in tools]}
        elif method == "tools/call":
            # Call a tool
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            req = CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(name=tool_name, arguments=tool_args),
            )
            response = await server.request_handlers[CallToolRequest](req)
            result = {"content": [c.model_dump(mode="json") for c in response.root.content]}
        elif method == "resources/list":
            # List resources
            req = ListResourcesRequest(method="resources/list")
            response = await server.request_handlers[ListResourcesRequest](req)
            resources = response.root.resources
            result = {"resources": [r.model_dump(mode="json") for r in resources]}
        elif method == "resources/read":
            # Read a resource
            uri = params.get("uri", "")
            req = ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(uri=uri),
            )
            response = await server.request_handlers[ReadResourceRequest](req)
            result = {"contents": [c.model_dump(mode="json") for c in response.root.contents]}
        else:
            return json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}",
                    },
                }
            )

        return json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result,
            }
        )

    except Exception as e:
        return json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": str(e),
                },
            }
        )

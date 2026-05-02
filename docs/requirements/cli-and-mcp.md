# CLI and MCP Requirements

Status flags:

- `[implemented]` - implemented by the current codebase.
- `[partial]` - partially implemented or implemented with important limitations.
- `[missing]` - not implemented by the current codebase.
- `[conflict]` - implemented current behavior that conflicts with a planned target requirement.
- `[delete]` - Function is deprecated and should be deleted


## CLI

- [implemented] `CLI-001` The CLI root command shall be named `circuitweaver`.
- [implemented] `CLI-002` `circuitweaver --version` shall report `circuitweaver.__version__`.
- [implemented] `CLI-003` `circuitweaver validate <input_file>` shall validate a Circuit JSON file.
- [implemented] [delete] `CLI-004` `circuitweaver validate` shall support `--output-format text` and `--output-format json`.
- [implemented] `CLI-005` `circuitweaver validate` shall exit with code `1` when validation has errors.
- [implemented] `CLI-006` `circuitweaver compile <file_path>` shall parse a Circuit JSON file and write KiCad files through `CompileEngine`.
- [implemented] `CLI-007` `circuitweaver compile` shall default output directory to `output`.
- [implemented] `CLI-008` `circuitweaver compile` shall default project name to `project`.
- [implemented] `CLI-009` `circuitweaver compile` shall support `--output-dir/-o` and `--name/-n`.
- [implemented] `CLI-010` `circuitweaver compile` shall exit with code `1` and print a traceback on failure.
- [implemented] `CLI-011` `circuitweaver erc <file_path>` shall run KiCad ERC for either a Circuit JSON input file or an existing `.kicad_sch` schematic path using the unified ERC flow.
- [implemented] `CLI-012` `circuitweaver erc` shall exit with code `1` if ERC execution raises.
- [implemented] `CLI-013` `circuitweaver search <query>` shall search KiCad parts.
- [implemented] `CLI-014` `circuitweaver search` shall pass `--limit` to part search and shall default the limit to `10` when the option is omitted.
- [implemented] `CLI-015` `circuitweaver pins <symbol_id>` shall print symbol pin number, name, and electrical type.
- [implemented] `CLI-016` `circuitweaver pins` shall exit with code `1` when symbol lookup raises `ValueError`.
- [implemented] `CLI-017` `circuitweaver serve` shall run the MCP server.
- [implemented] `CLI-018` `circuitweaver serve` shall support `--transport stdio` for local MCP clients and `--transport http` for optional hosted use, defaulting to `stdio`.
- [implemented] `CLI-019` `circuitweaver serve` shall support `--tools` as a comma-separated allowlist of enabled MCP tool names and shall exit with a clear error if any requested tool is unknown.
- [implemented] `CLI-020` `circuitweaver serve` shall support `--port`, defaulting to `3000`.
- [implemented] `CLI-021` `circuitweaver serve` shall support `--host`, defaulting to `localhost`.
- [implemented] `CLI-022` `circuitweaver info` shall print package version and detected KiCad library paths.
- [implemented] `CLI-023` `python -m circuitweaver` shall run the same CLI entry point.

## MCP Server

- [implemented] `MCP-001` The MCP server name shall be `circuitweaver`.
- [implemented] `MCP-002` If `enabled_tools` is not provided, all tools in `TOOL_REGISTRY` shall be exposed.
- [implemented] `MCP-003` If `enabled_tools` is provided, only matching tool names from `TOOL_REGISTRY` shall be exposed.
- [implemented] `MCP-004` Unknown names in `enabled_tools` shall raise `ValueError` naming the unknown tool or tools.
- [implemented] `MCP-005` `list_tools` shall return MCP `Tool` definitions generated from the active tool handlers.
- [implemented] `MCP-006` Calling an unknown tool shall return text content `Unknown tool: <name>`.
- [implemented] `MCP-007` Tool handler exceptions shall be caught and returned as text content beginning with `Error:`.
- [implemented] `MCP-008` Tool parameters shall be converted into JSON schema object properties with type, description, optional enum, optional default, and a required list.

## MCP Tools

- [implemented] `MCP-020` `search_kicad_parts` shall accept required `query` text matched case-insensitively against KiCad library IDs, names, descriptions, and keywords, and optional positive integer `limit` defaulting to `10`.
- [implemented] `MCP-021` `search_kicad_parts` shall return a structured result with human-readable summary text and a `parts` array containing library ID, library name, symbol name, description, keywords, footprint, and datasheet fields when available.
- [implemented] `MCP-022` `get_symbol_pins` shall accept `symbol_id`.
- [implemented] `MCP-023` `get_symbol_pins` shall return a structured result with human-readable summary text and a `pins` array containing pin number, name, electrical type, direction, and grid offset.
- [implemented] `MCP-024` `get_symbol_pins` shall return a structured error result when symbol lookup fails.
- [implemented] `MCP-025` `validate_circuit_json` shall accept `file_path`.
- [implemented] `MCP-026` `validate_circuit_json` shall reject invalid paths, missing files, and non-files with structured error results.
- [implemented] `MCP-027` `validate_circuit_json` shall return a structured success result when validation has no errors.
- [implemented] `MCP-028` `validate_circuit_json` shall return a structured failure result with validation errors when errors exist.
- [implemented] `MCP-029` `create_schematic` shall accept required `file_path` for the input Circuit JSON file plus optional `output_dir`, `project_name`, `write_schematic_json`, `write_kicad`, `write_debug_layout`, and backward-compatible `debug` parameters.
- [implemented] `MCP-030` `create_schematic` shall read a Circuit JSON file, run layout, and write only the requested outputs to the explicit output directory when provided, or beside the input file when no output directory is provided.
- [implemented] `MCP-031` `create_schematic` shall report every created output path in a structured `outputs` list.
- [implemented] `MCP-032` `run_erc` shall accept `file_path` for either a Circuit JSON file or an existing `.kicad_sch` file.
- [implemented] `MCP-033` `run_erc` shall use the unified ERC flow and return structured ERC errors, warnings, generated artifact metadata, and human-readable summary text.
- [implemented] `MCP-034` CircuitWeaver MCP shall expose only CircuitWeaver domain tools from `TOOL_REGISTRY`.

## MCP Resources

- [implemented] `MCP-040` The server shall expose `circuitweaver://docs/readme`.
- [implemented] `MCP-041` The server shall expose `circuitweaver://docs/install`.
- [implemented] `MCP-042` The server shall expose `circuitweaver://docs/mcp-workflow`.
- [implemented] `MCP-043` The server shall expose `circuitweaver://tools/reference`.
- [implemented] `MCP-044` The server shall expose `circuitweaver://docs/circuit-json-spec`.
- [implemented] `MCP-045` The server shall expose `circuitweaver://docs/troubleshooting`.
- [implemented] `MCP-046` The server shall expose `circuitweaver://examples/simple-led`.
- [implemented] `MCP-047` The server shall expose `circuitweaver://docs/examples`.
- [implemented] `MCP-048` Unknown resource URIs shall raise `ValueError`.
- [implemented] `MCP-049` `circuitweaver://tools/reference` shall be generated from the currently active tool set.
- [implemented] `MCP-050` Resource file loading shall support both installed wheels and source-tree development by first trying package-included resources under `circuitweaver`, then falling back to repository-relative files.

## MCP Prompts

- [implemented] `MCP-060` The server shall expose one prompt named `design-guidelines`.
- [implemented] `MCP-061` `design-guidelines` shall instruct clients to load workflow, tool reference, spec, and example resources when available.
- [implemented] `MCP-062` `design-guidelines` shall instruct clients to use client-native file tools for JSON file creation/editing.
- [implemented] `MCP-063` `design-guidelines` shall instruct clients to use CircuitWeaver tools only for CircuitWeaver-specific operations.
- [implemented] `MCP-064` Unknown prompt names shall raise `ValueError` so MCP clients receive an explicit protocol error for unsupported prompt requests.

## MCP Transports

- [implemented] `MCP-070` Stdio transport shall use `mcp.server.stdio.stdio_server`.
- [implemented] `MCP-071` HTTP transport shall import `uvicorn` and `create_http_app`.
- [implemented] `MCP-072` HTTP transport import failure shall raise `ImportError` instructing installation of `circuitweaver[http]`.
- [implemented] `MCP-073` HTTP transport shall run `uvicorn.run(app, host=host, port=port)`.
- [implemented] `MCP-074` Unsupported transport names shall raise `ValueError`.
- [implemented] `MCP-075` The custom HTTP app shall expose `GET /` and `GET /health` health endpoints.
- [partial] `MCP-076` The custom HTTP app shall expose `POST /mcp` for simplified JSON-RPC handling until a standards-compliant MCP HTTP transport is available in the installed MCP SDK.
- [implemented] `MCP-077` The custom HTTP app shall not expose placeholder SSE protocol endpoints.
- [partial] `MCP-078` The custom HTTP JSON-RPC handler shall implement `tools/list`, `tools/call`, `resources/list`, and `resources/read` as a compatibility transport, not as a standards-compliant MCP HTTP implementation.
- [implemented] `MCP-079` Unsupported HTTP JSON-RPC methods shall return JSON-RPC error code `-32601`.
- [implemented] `MCP-080` HTTP handler exceptions shall return JSON-RPC error code `-32603`.

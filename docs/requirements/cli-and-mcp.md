# CLI and MCP Requirements

Status flags:

- `[implemented]` - implemented by the current codebase.
- `[partial]` - partially implemented or implemented with important limitations.
- `[missing]` - not implemented by the current codebase.
- `[conflict]` - implemented current behavior that conflicts with a planned target requirement.

## CLI

- [implemented] `CLI-001` The CLI root command shall be named `circuitweaver`.
- [implemented] `CLI-002` `circuitweaver --version` shall report `circuitweaver.__version__`.
- [implemented] `CLI-003` `circuitweaver validate <input_file>` shall validate a Circuit JSON file.
- [implemented] `CLI-004` `circuitweaver validate` shall support `--output-format text` and `--output-format json`.
- [implemented] `CLI-005` `circuitweaver validate` shall exit with code `1` when validation has errors.
- [implemented] `CLI-006` `circuitweaver compile <file_path>` shall parse a Circuit JSON file and write KiCad files through `CompileEngine`.
- [implemented] `CLI-007` `circuitweaver compile` shall default output directory to `output`.
- [implemented] `CLI-008` `circuitweaver compile` shall default project name to `project`.
- [implemented] `CLI-009` `circuitweaver compile` shall support `--output-dir/-o` and `--name/-n`.
- [implemented] `CLI-010` `circuitweaver compile` shall exit with code `1` and print a traceback on failure.
- [conflict] `CLI-011` `circuitweaver erc <schematic_path>` shall run KiCad ERC through `ERCChecker`. This current CLI-only schematic input model conflicts with planned unified ERC input requirements `ARCH-080`, `ARCH-081`, and `ARCH-082`.
- [implemented] `CLI-012` `circuitweaver erc` shall exit with code `1` if ERC execution raises.
- [implemented] `CLI-013` `circuitweaver search <query>` shall search KiCad parts.
- [implemented] `CLI-014` `circuitweaver search` shall support `--limit`, defaulting to `10`.
- [implemented] `CLI-015` `circuitweaver pins <symbol_id>` shall print symbol pin number, name, and electrical type.
- [implemented] `CLI-016` `circuitweaver pins` shall exit with code `1` when symbol lookup raises `ValueError`.
- [implemented] `CLI-017` `circuitweaver serve` shall run the MCP server.
- [implemented] `CLI-018` `circuitweaver serve` shall support `--transport stdio` and `--transport http`, defaulting to `stdio`.
- [implemented] `CLI-019` `circuitweaver serve` shall support `--tools` as a comma-separated allowlist of enabled MCP tool names.
- [implemented] `CLI-020` `circuitweaver serve` shall support `--port`, defaulting to `3000`.
- [implemented] `CLI-021` `circuitweaver serve` shall support `--host`, defaulting to `localhost`.
- [implemented] `CLI-022` `circuitweaver info` shall print package version and detected KiCad library paths.
- [implemented] `CLI-023` `python -m circuitweaver` shall run the same CLI entry point.

## MCP Server

- [implemented] `MCP-001` The MCP server name shall be `circuitweaver`.
- [implemented] `MCP-002` If `enabled_tools` is not provided, all tools in `TOOL_REGISTRY` shall be exposed.
- [implemented] `MCP-003` If `enabled_tools` is provided, only matching tool names from `TOOL_REGISTRY` shall be exposed.
- [implemented] `MCP-004` Unknown names in `enabled_tools` shall be silently ignored.
- [implemented] `MCP-005` `list_tools` shall return MCP `Tool` definitions generated from the active tool handlers.
- [implemented] `MCP-006` Calling an unknown tool shall return text content `Unknown tool: <name>`.
- [implemented] `MCP-007` Tool handler exceptions shall be caught and returned as text content beginning with `Error:`.
- [implemented] `MCP-008` Tool parameters shall be converted into JSON schema object properties with type, description, optional enum, optional default, and a required list.

## MCP Tools

- [implemented] `MCP-020` `search_kicad_parts` shall accept `query` and optional `limit`.
- [conflict] `MCP-021` `search_kicad_parts` shall return a human-readable string listing library IDs and optional description/footprint, or a no-results message. This conflicts with planned structured result requirements `MCPR-001`, `MCPR-003`, and `MCPR-004`.
- [implemented] `MCP-022` `get_symbol_pins` shall accept `symbol_id`.
- [conflict] `MCP-023` `get_symbol_pins` shall return a Markdown table with pin number, name, and electrical type. This conflicts with planned structured pin result requirements `MCPR-001`, `MCPR-003`, and `MCPR-005`.
- [conflict] `MCP-024` `get_symbol_pins` shall return an error string when symbol lookup fails. This conflicts with planned structured error requirements `MCPR-001` and `MCPR-002`.
- [implemented] `MCP-025` `validate_circuit_json` shall accept `file_path`.
- [implemented] `MCP-026` `validate_circuit_json` shall reject invalid paths, missing files, and non-files with error strings.
- [conflict] `MCP-027` `validate_circuit_json` shall return `SUCCESS` text when validation has no errors. This conflicts with planned structured validation result requirements `MCPR-001`, `MCPR-002`, and `MCPR-006`.
- [conflict] `MCP-028` `validate_circuit_json` shall return `FAILED` text and list errors when validation has errors. This conflicts with planned structured validation result requirements `MCPR-001`, `MCPR-002`, and `MCPR-006`.
- [implemented] `MCP-029` `create_schematic` shall accept `file_path` and optional `debug`.
- [conflict] `MCP-030` `create_schematic` shall read a Circuit JSON file, run layout, write `<stem>_schematic.json`, and write `<stem>.kicad_sch` and `<stem>.kicad_pro` in the same directory. This conflicts with planned explicit output control requirements `ARCH-040`, `ARCH-041`, `ARCH-042`, `ARCH-043`, and `ARCH-044`.
- [implemented] `MCP-031` `create_schematic(debug=true)` shall additionally write ELK debug input/output files.
- [implemented] `MCP-032` `run_erc` shall accept `file_path`.
- [conflict] `MCP-033` `run_erc` shall read Circuit JSON, compile it in a temporary directory, run ERC on the generated root schematic, and return success/failure text. This conflicts with planned unified ERC and structured result requirements `ARCH-080`, `ARCH-082`, `ARCH-083`, and `MCPR-008`.
- [implemented] `MCP-034` CircuitWeaver MCP shall not expose generic file editing tools such as `read_file`, `write_file`, or `edit_file`.

## MCP Resources

- [implemented] `MCP-040` The server shall expose `circuitweaver://docs/readme`.
- [implemented] `MCP-041` The server shall expose `circuitweaver://docs/install`.
- [implemented] `MCP-042` The server shall expose `circuitweaver://docs/mcp-workflow`.
- [implemented] `MCP-043` The server shall expose `circuitweaver://tools/reference`.
- [implemented] `MCP-044` The server shall expose `circuitweaver://docs/circuit-json-spec`.
- [implemented] `MCP-045` The server shall expose `circuitweaver://docs/troubleshooting`.
- [implemented] `MCP-046` The server shall expose `circuitweaver://examples/simple-led`.
- [implemented] `MCP-047` The server shall expose `circuitweaver://docs/examples` as an alias for the simple LED example.
- [implemented] `MCP-048` Unknown resource URIs shall raise `ValueError`.
- [implemented] `MCP-049` `circuitweaver://tools/reference` shall be generated from the currently active tool set.
- [implemented] `MCP-050` Resource file loading shall first try packaged files under the `circuitweaver` package and then fall back to source-tree files.

## MCP Prompts

- [implemented] `MCP-060` The server shall expose one prompt named `design-guidelines`.
- [implemented] `MCP-061` `design-guidelines` shall instruct clients to load workflow, tool reference, spec, and example resources when available.
- [implemented] `MCP-062` `design-guidelines` shall instruct clients to use client-native file tools for JSON file creation/editing.
- [implemented] `MCP-063` `design-guidelines` shall instruct clients to use CircuitWeaver tools only for CircuitWeaver-specific operations.
- [implemented] `MCP-064` Unknown prompt names shall raise `ValueError`.

## MCP Transports

- [implemented] `MCP-070` Stdio transport shall use `mcp.server.stdio.stdio_server`.
- [implemented] `MCP-071` HTTP transport shall import `uvicorn` and `create_http_app`.
- [implemented] `MCP-072` HTTP transport import failure shall raise `ImportError` instructing installation of `circuitweaver[http]`.
- [implemented] `MCP-073` HTTP transport shall run `uvicorn.run(app, host=host, port=port)`.
- [implemented] `MCP-074` Unsupported transport names shall raise `ValueError`.
- [implemented] `MCP-075` The custom HTTP app shall expose `GET /` and `GET /health` health endpoints.
- [conflict] `MCP-076` The custom HTTP app shall expose `POST /mcp` for simplified JSON-RPC handling. This conflicts with planned standards-compliant HTTP MCP transport requirement `ARCH-060`.
- [conflict] `MCP-077` The custom HTTP app shall expose `GET /mcp/sse` that currently emits a placeholder connected event. This conflicts with planned replacement/removal requirement `ARCH-063`.
- [conflict] `MCP-078` The custom HTTP JSON-RPC handler shall implement `tools/list`, `tools/call`, `resources/list`, and `resources/read`. This conflicts with planned standards-compliant HTTP MCP transport requirement `ARCH-060`.
- [implemented] `MCP-079` Unsupported HTTP JSON-RPC methods shall return JSON-RPC error code `-32601`.
- [implemented] `MCP-080` HTTP handler exceptions shall return JSON-RPC error code `-32603`.

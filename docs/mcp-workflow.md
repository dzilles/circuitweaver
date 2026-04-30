# CircuitWeaver MCP Workflow

Use this workflow when designing or modifying circuits through an MCP client.

## 1. Load Reference Material

Read these resources before creating Circuit JSON:

- `circuitweaver://tools/reference` for the tools available in the current server session.
- `circuitweaver://docs/circuit-json-spec` for the Circuit JSON schema and design rules.
- `circuitweaver://examples/simple-led` when a compact example is useful.

## 2. Research Components

Use CircuitWeaver tools for KiCad-specific lookup:

- `search_kicad_parts` to find KiCad library IDs.
- `get_symbol_pins` to confirm exact pin numbers and names before creating `source_port` elements.

Only assign a footprint when you are confident the KiCad footprint string is correct. It is better to omit a footprint than to invent one.

## 3. Create Or Edit Circuit JSON

Use the MCP client's normal file tools to write a JSON file. CircuitWeaver does not expose generic file-editing tools.

Start with logic-only `source_*` elements:

- `source_component`
- `source_port`
- `source_net`
- `source_trace`
- `source_group`

## 4. Validate

Call `validate_circuit_json` on the JSON file and fix all errors before creating schematics.

## 5. Generate Schematics

Call `create_schematic` with the Circuit JSON file path. It will:

- Run auto-layout.
- Write `<name>_schematic.json`.
- Write `<name>.kicad_sch`.
- Write `<name>.kicad_pro`.

Use `debug: true` only when you need ELK layout input/output files for troubleshooting.

## 6. Run ERC

Call `run_erc` with the Circuit JSON file path. This compiles the design in a temporary directory and runs KiCad ERC on the generated schematic.

If ERC reports errors, fix the source JSON and repeat validation, schematic generation, and ERC.

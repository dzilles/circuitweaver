# Implementation Notes and Gaps

These items are requirements only in the sense that they describe current
implementation boundaries. They should be considered when writing tests or
planning changes.

## Active Versus Inactive Validation Rules

- [implemented] `GAP-001` `validate_circuit_file` and `validate_circuit_elements` use named `VALIDATION_PROFILES`; the legacy `VALIDATION_RULES` list is not the source of profile behavior.
- [partial] `GAP-002` The following rule files exist but are not active in any `VALIDATION_PROFILES` entry: `bounds_check.py`, `hierarchy_links.py`, `integer_coords.py`, `orthogonal_traces.py`, `pin_positions.py`, `source_first.py`, `unconnected_pins.py`, and `unplaced_components.py`. This remains cleanup work for `VALP-007`.
- [conflict] `GAP-003` Inactive validation rules shall not be used as a source of current validation behavior unless they are first activated and reconciled with the current data models. This conflicts with planned cleanup requirement `VALP-007`.
- [conflict] `GAP-004` Some inactive validation rules reference fields or classes that are not present in the current data models; tests for current behavior should not assume those rules run. This conflicts with planned cleanup requirement `VALP-007`.

## Validation Scope

- [implemented] `GAP-010` The `source` profile checks source ID namespaces; the `schematic` profile adds schematic ID checks.
- [implemented] `GAP-011` The `schematic` profile validates schematic references such as `SchematicComponent.source_component_id` and `SchematicPort.source_port_id`.
- [partial] `GAP-012` Active validation can require KiCad symbol libraries when `SourceComponent.symbol_id` is present because `SourcePortCompletenessRule` calls `get_symbol_info`. This is implemented, but dependency readiness should become profile- and environment-aware under `VALP-004`, `VALP-005`, and `DOCTOR-005`.
- [partial] `GAP-013` A design without `symbol_id` values may validate with warnings even though generated KiCad symbol fidelity will be limited. This is implemented, but compile readiness should be reported explicitly under `VALP-004`.

## Layout And Compilation Constraints

- [partial] `GAP-020` Auto-layout depends on external Node.js and `elkjs`; it is not pure Python. This dependency is implemented, but planned diagnostics in `DOCTOR-003` and `DOCTOR-004` are missing.
- [implemented] `GAP-021` `CompileEngine.compile` checks whether the schematic layer is complete before reusing it; incomplete schematic layers run auto-layout.
- [partial] `GAP-022` `CompileEngine.compile` returns the root schematic path, but that path may remain `None` internally if no root sheet is written. This conflicts with the reliability goal behind `ARCH-005`.
- [partial] `GAP-023` Debug ELK files may be written either to explicit debug paths or to the current working directory when `CIRCUITWEAVER_DEBUG_ELK` is enabled. This is implemented, but planned in-memory intermediate artifacts in `ARCH-006` are missing.
- [implemented] `GAP-024` Hierarchical net processing no longer relies on hard-coded substring matching only; it uses explicit source net flags, project global-net configuration, and optional KiCad power-symbol defaults.
- [implemented] `GAP-025` The root sheet creates label-based connections between matching hierarchical sheet pins for non-global inter-sheet nets.
- [partial] `GAP-026` Global inter-sheet labels depend on source ports being mappable to schematic ports. Designs with incomplete source port pin metadata may not get fully connected global labels until port mapping is improved.

## KiCad Output Constraints

- [implemented] `GAP-030` KiCad output targets KiCad schematic version `20260306` and generator version `10.0`.
- [partial] `GAP-031` KiCad symbol embedding depends on local KiCad library files. This dependency is implemented, but planned diagnostics in `DOCTOR-005` are missing.
- [conflict] `GAP-032` If symbol embedding fails, the failure is logged and compilation continues. This conflicts with planned structured failure reporting in `ARCH-005` and compile-readiness validation in `VALP-004`.
- [partial] `GAP-033` Missing or invalid component symbols may still fall back to `Device:QuestionBlock` in S-expression generation when neither `symbol_id` nor `ftype` can provide an effective symbol ID. This conflicts with planned compile-readiness validation in `VALP-004` unless fallback behavior is made explicit and caller-controlled.
- [implemented] `GAP-034` KiCad S-expression generation supports deterministic UUID injection for tests; default production UUID generation remains nondeterministic.

## MCP And HTTP Constraints

- [implemented] `GAP-040` MCP prompts and resources are exposed to clients but are not automatically inserted into the model context by the server.
- [implemented] `GAP-041` Whether prompts/resources are automatically loaded is client-dependent.
- [conflict] `GAP-042` The custom HTTP transport is a simplified JSON-RPC wrapper and not a full Streamable HTTP MCP implementation. This conflicts with planned standards-compliant HTTP transport requirement `ARCH-060`.
- [conflict] `GAP-043` The custom SSE endpoint currently sends only a placeholder connected event. This conflicts with planned replacement/removal requirement `ARCH-063`.
- [partial] `GAP-044` MCP `--tools` filtering affects exposed tools and generated tool reference resources, but does not rewrite the static prompt text beyond telling clients to consult the tool reference. This is implemented, but tool-scoped prompt/resource generation remains limited.

## CLI Constraints

- [conflict] `GAP-050` CLI `compile` parses JSON through Pydantic but does not run `validate_circuit_file` before compiling. This conflicts with planned pipeline validation requirements `ARCH-001`, `ARCH-005`, and `VALP-004`.
- [conflict] `GAP-051` CLI `erc` accepts a generated schematic path, while MCP `run_erc` accepts a Circuit JSON path and compiles temporarily before ERC. This conflicts with planned unified ERC requirements `ARCH-080` through `ARCH-083`.
- [partial] `GAP-052` CLI command failures generally print human-readable output rather than structured JSON, except `validate --output-format json`. This is implemented, but structured output is incomplete compared with planned result contracts `ARCH-005` and `ARCH-083`.

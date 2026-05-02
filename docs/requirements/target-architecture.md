# Target Architecture Requirements

These requirements describe planned improvements. They are not implemented by
the current codebase unless explicitly marked otherwise.

Status flags:

- `[implemented]` - implemented by the current codebase.
- `[partial]` - partially implemented or implemented with important limitations.
- `[missing]` - not implemented by the current codebase.
- `[conflict]` - implemented or documented current behavior that conflicts with a planned target requirement.

## Compiler Architecture

- [partial] `ARCH-001` The compiler shall expose separate parse, validate, layout, schematic, KiCad transform, and write stages.
  `CompileEngine` exposes stage methods for parse, validate, layout, schematic, KiCad transform, and write. Validation is still path-backed when using existing validation rules, and the legacy `compile` wrapper remains.
- [implemented] `ARCH-002` The compiler shall provide a pure in-memory pipeline that can run through schematic and KiCad S-expression generation without writing files.
  `CompileEngine.kicad_project()` returns in-memory schematic S-expressions and project JSON content.
- [partial] `ARCH-003` File-writing shall be isolated in an explicit output stage.
  KiCad output writing is isolated in `CompileEngine.write_kicad()`. ELK debug files can still be written by the layout stage when debug paths or `CIRCUITWEAVER_DEBUG_ELK` are used.
- [missing] `ARCH-004` The compiler shall not skip auto-layout solely because any schematic element is present; it shall validate whether the schematic layer is complete for the requested operation.
- [partial] `ARCH-005` Pipeline stages shall return structured result objects instead of relying on exceptions and side effects for normal failure reporting.
  New stage methods return `StageResult` objects. Existing lower-level layout, routing, symbol lookup, and compatibility APIs still raise exceptions for some failures.
- [partial] `ARCH-006` The compilation pipeline shall expose intermediate artifacts for tests without requiring debug files on disk.
  Stage results expose schematic and KiCad artifact metadata. Raw ELK input/output artifacts are still only available through debug files.

## Project Model

- [implemented] `ARCH-020` CircuitWeaver shall provide a first-class `CircuitProject` object.
- [implemented] `ARCH-021` `CircuitProject` shall separate source elements, schematic elements, generated layout artifacts, and project metadata.
- [partial] `ARCH-022` Pipeline stages shall accept and return `CircuitProject` or dedicated stage result types instead of passing a raw `list[CircuitElement]` through all stages.
  New stage methods use `CircuitProject` and `StageResult`. Legacy transform internals still use `list[CircuitElement]`.
- [implemented] `ARCH-023` `CircuitProject` shall provide typed accessors for source components, ports, nets, traces, groups, and schematic elements.

## Validation Profiles

- [missing] `VALP-001` Validation shall support named profiles.
- [missing] `VALP-002` The `source` validation profile shall validate logic-only Circuit JSON for schema, source IDs, source references, trace connectivity, and source port completeness.
- [missing] `VALP-003` The `schematic` validation profile shall validate schematic elements, schematic references, geometry, labels, ports, and no-connects.
- [missing] `VALP-004` The `compile-ready` validation profile shall validate that a design has enough information and environment support to generate KiCad files.
- [missing] `VALP-005` The `erc-ready` validation profile shall validate that generated KiCad files and `kicad-cli` are available for ERC.
- [missing] `VALP-006` Validation results shall report which profile produced each error or warning.
- [missing] `VALP-007` Inactive validation rules shall either be updated and activated under a profile or removed from the active source tree.

## Structured MCP Results

- [implemented] `MCPR-001` MCP tools shall return structured result objects.
- [implemented] `MCPR-002` Structured MCP results shall include `ok`, `errors`, `warnings`, and `outputs`.
- [implemented] `MCPR-003` Human-readable text may be included in structured MCP results, but shall not be the only machine-readable result.
- [implemented] `MCPR-004` `search_kicad_parts` shall return structured part records with library ID, library name, symbol name, description, keywords, footprint, and datasheet fields when available.
- [implemented] `MCPR-005` `get_symbol_pins` shall return structured pin records with number, name, electrical type, direction, and grid offset.
- [implemented] `MCPR-006` `validate_circuit_json` shall return structured validation errors and warnings equivalent to `ValidationResult.to_dict`.
- [implemented] `MCPR-007` `create_schematic` shall return structured output file paths and generated artifact metadata.
- [implemented] `MCPR-008` `run_erc` shall return structured ERC errors, warnings, and generated temporary artifact metadata.

## Explicit Output Control

- [implemented] `ARCH-040` `create_schematic` shall accept an explicit output directory.
- [implemented] `ARCH-041` `create_schematic` shall accept an explicit project name.
- [implemented] `ARCH-042` `create_schematic` shall provide explicit flags for writing schematic JSON, KiCad files, and debug layout files.
- [implemented] `ARCH-043` MCP tools that write files shall report every created or modified path in a structured output list.
- [implemented] `ARCH-044` MCP tools shall avoid surprising writes beside the input file unless the caller explicitly requests that behavior or no output directory is provided.

## Environment Diagnostics

- [missing] `DOCTOR-001` The CLI shall provide `circuitweaver doctor`.
- [missing] `DOCTOR-002` `circuitweaver doctor` shall check Python package version and importability.
- [missing] `DOCTOR-003` `circuitweaver doctor` shall check that Node.js is available.
- [missing] `DOCTOR-004` `circuitweaver doctor` shall check that `elkjs` is resolvable from the current runtime.
- [missing] `DOCTOR-005` `circuitweaver doctor` shall check detected KiCad symbol, footprint, 3D model, and template paths.
- [missing] `DOCTOR-006` `circuitweaver doctor` shall check that `kicad-cli` is available.
- [missing] `DOCTOR-007` `circuitweaver doctor` shall check that packaged MCP resources can be read.
- [missing] `DOCTOR-008` `circuitweaver doctor` shall support machine-readable JSON output.

## HTTP MCP Transport

- [partial] `ARCH-060` HTTP MCP support shall use an official MCP SDK Streamable HTTP transport or another standards-compliant MCP HTTP transport.
  The current implementation retains a simplified JSON-RPC compatibility endpoint because the local environment does not provide an inspectable MCP SDK HTTP transport.
- [missing] `ARCH-061` Hosted HTTP MCP support shall support authentication hooks.
- [missing] `ARCH-062` Hosted HTTP MCP support shall support request limits or quota hooks.
- [implemented] `ARCH-063` The placeholder SSE endpoint shall be removed or replaced with a functional protocol endpoint.

## ERC Behavior

- [implemented] `ARCH-080` CLI and MCP ERC behavior shall use a unified input model.
- [implemented] `ARCH-081` ERC shall support running from a Circuit JSON input by compiling to a controlled output or temporary directory.
- [implemented] `ARCH-082` ERC shall support running from an existing `.kicad_sch` path.
- [implemented] `ARCH-083` ERC result objects shall use the same structured result schema across CLI, MCP, and Python API entry points.

## Testability and Determinism

- [missing] `TEST-001` KiCad S-expression generation shall support deterministic UUID generation for tests.
- [missing] `TEST-002` Compile pipeline tests shall be able to inject symbol lookup, router, and ERC dependencies without monkeypatching module imports.
- [missing] `TEST-003` Requirement-to-test traceability shall be machine-checkable for all requirement files, not only CLI/MCP requirements.

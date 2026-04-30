# CircuitWeaver Implementation Requirements

These requirements describe both the behavior implemented by the current
codebase and the target behavior planned for future work. They are intended as
a basis for implementation planning and tests.

The status flag on each requirement defines how it relates to the current
codebase.

## Status Flags

- `[implemented]` - implemented by the current codebase.
- `[partial]` - partially implemented or implemented with important limitations.
- `[missing]` - not implemented by the current codebase.
- `[conflict]` - implemented or documented current behavior that conflicts with a planned target requirement.

## Files

- [runtime-and-packaging.md](runtime-and-packaging.md) - package metadata, dependencies, installable assets, and runtime prerequisites.
- [data-model.md](data-model.md) - Circuit JSON, layout graph, and S-expression data structures.
- [io-and-validation.md](io-and-validation.md) - JSON I/O, S-expression I/O, validation flow, and active validation rules.
- [layout-and-compilation.md](layout-and-compilation.md) - source-to-layout, ELK routing, schematic generation, and KiCad file writing.
- [kicad-library-and-erc.md](kicad-library-and-erc.md) - KiCad path discovery, part search, symbol pinout extraction, and ERC parsing.
- [cli-and-mcp.md](cli-and-mcp.md) - command-line interface, MCP tools, MCP resources, MCP prompts, and HTTP transport behavior.
- [implementation-notes-and-gaps.md](implementation-notes-and-gaps.md) - current constraints, inactive code, and behavior that should not be assumed.
- [target-architecture.md](target-architecture.md) - planned improvements that are not yet implemented.

## Requirement ID Convention

Requirement IDs use a short area prefix:

- `PKG` - packaging and runtime
- `DM` - data model
- `IO` - I/O
- `VAL` - validation
- `LAY` - layout
- `CMP` - compilation
- `KICAD` - KiCad libraries and symbols
- `ERC` - electrical rules check
- `CLI` - command-line interface
- `MCP` - MCP server behavior
- `GAP` - current limitations or implementation gaps
- `ARCH` - target architecture and pipeline structure
- `VALP` - target validation profiles
- `MCPR` - target MCP response contracts
- `DOCTOR` - target environment diagnostics
- `TEST` - target testability and determinism

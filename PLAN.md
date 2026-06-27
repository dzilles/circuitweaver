# Historical Plan

This file is retained only as historical context. The old Phase 1 plan proposed
a clean-slate removal of all `schematic_*` types, but that is no longer the
project direction.

Current direction:

1. User-authored Circuit JSON should normally contain source-layer `source_*`
   elements.
2. CircuitWeaver derives a canonical connectivity model from those source
   elements.
3. Auto-layout generates visual `schematic_*` elements as internal/debug
   artifacts.
4. The KiCad writer serializes the generated schematic model to native KiCad
   files.

Use the current implementation plan instead:

- [docs/kiss-connectivity-refactor-plan.md](docs/kiss-connectivity-refactor-plan.md)

For authoring guidance, use:

- [docs/circuit-json-spec.md](docs/circuit-json-spec.md)
- [docs/mcp-workflow.md](docs/mcp-workflow.md)
- [examples/simple_led/circuit.json](examples/simple_led/circuit.json)

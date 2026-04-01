# CircuitWeaver

An MCP (Model Context Protocol) server for generating KiCad schematics from Circuit JSON format.

CircuitWeaver enables AI assistants like Claude and Gemini to design and generate professional electronic schematics through a structured JSON format that compiles to native KiCad files.

## Features

- **Circuit JSON Format**: A human-readable JSON schema for describing electronic circuits
- **KiCad Integration**: Compiles to native `.kicad_sch` schematic files
- **Validation Engine**: Catches errors before compilation (orthogonal traces, grid alignment, etc.)
- **ERC Support**: Electrical Rules Check via KiCad CLI
- **MCP Server**: Integrates with Claude Code, Gemini CLI, and other MCP-compatible tools
- **Hierarchical Schematics**: Support for multi-sheet designs with proper hierarchy

## Requirements

- Python 3.11 or higher
- KiCad 10.0+ (for compilation and ERC features)

## Installation

```bash
# Install from PyPI (when published)
pip install circuitweaver

# Or install from source
git clone https://github.com/yourusername/circuitweaver.git
cd circuitweaver
pip install -e .
```

## Quick Start

### 1. Add to Claude Code

```bash
# Add CircuitWeaver as an MCP server
claude mcp add circuitweaver -- python -m circuitweaver serve
```

### 2. Use in Conversation

Once added, Claude can use CircuitWeaver tools to:
- Search KiCad part libraries
- Get component pinouts
- Validate Circuit JSON designs
- Compile to KiCad schematics
- Run electrical rules checks

### 3. Standalone CLI

```bash
# Validate a Circuit JSON file
circuitweaver validate design.json

# Compile to KiCad schematic
circuitweaver compile design.json -o output/

# Run ERC on generated schematic
circuitweaver erc output/main.kicad_sch

# Start MCP server (stdio mode)
circuitweaver serve

# Start MCP server (HTTP mode, requires [http] extras)
circuitweaver serve --transport http --port 3000
```

## Circuit JSON Format

CircuitWeaver uses a two-layer architecture:

### Source Types (Logical Layer)
Define **what** exists in the circuit:
- `source_component`: Part definition (value, footprint, MPN)
- `source_port`: Pin/terminal on a component
- `source_net`: Named electrical net
- `source_trace`: Logical connection

### Schematic Types (Visual Layer)
Define **where** things appear:
- `schematic_component`: Visual placement of a component
- `schematic_port`: Connection point on a component
- `schematic_trace`: Wire connecting ports
- `schematic_box`: Visual grouping box
- `schematic_net_label`: Net name label

### Example

```json
[
  {
    "type": "source_component",
    "source_component_id": "src_r1",
    "name": "R1",
    "value": "10k",
    "footprint": "Resistor_SMD:R_0603_1608Metric"
  },
  {
    "type": "schematic_component",
    "schematic_component_id": "sch_r1",
    "source_component_id": "src_r1",
    "center": { "x": 20, "y": 30 },
    "rotation": 0
  }
]
```

See [Circuit JSON Specification](docs/circuit-json-spec.md) for the complete format.

## MCP Tools

CircuitWeaver exposes the following tools via MCP:

| Tool | Description | Requires KiCad |
|------|-------------|----------------|
| `search_kicad_parts` | Search component libraries | No |
| `get_symbol_pinout` | Get pin positions for a symbol | No* |
| `validate_circuit_file` | Validate Circuit JSON | No |
| `compile_to_kicad` | Generate .kicad_sch files | Yes |
| `run_erc` | Run electrical rules check | Yes |
| `read_file` | Read file contents | No |
| `write_file` | Write file contents | No |
| `edit_file` | Edit file contents | No |

*Bundled symbols don't require KiCad; custom libraries do.

## Development

```bash
# Clone and install with dev dependencies
git clone https://github.com/yourusername/circuitweaver.git
cd circuitweaver
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check src/

# Run type checker
mypy src/

# Run all checks
pre-commit run --all-files
```

## Project Structure

```
circuitweaver/
├── src/circuitweaver/
│   ├── cli.py              # CLI entry point
│   ├── server/             # MCP server implementation
│   ├── tools/              # Tool implementations
│   ├── types/              # Pydantic models
│   ├── compiler/           # Circuit JSON → KiCad compiler
│   ├── validator/          # Validation engine
│   ├── library/            # KiCad library interface
│   ├── erc/                # Electrical rules checker
│   └── utils/              # Shared utilities
├── tests/                  # Test suite
├── docs/                   # Documentation
└── examples/               # Example circuits
```

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details.

## Acknowledgments

- [KiCad](https://www.kicad.org/) - The open source EDA suite
- [Anthropic MCP](https://github.com/anthropics/mcp) - Model Context Protocol
- [tscircuit](https://github.com/tscircuit/tscircuit) - Inspiration for Circuit JSON format

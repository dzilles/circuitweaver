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
- Node.js 18+ and `elkjs` (for automatic schematic layout)
- KiCad 10.0+ (for KiCad library search, compilation, and ERC features)

## Installation

CircuitWeaver can be installed directly from this repository. The Python package is installed with `pip`; the auto-layout engine also needs the Node package `elkjs`.

### Linux

```bash
# From the repository root
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install .

# Install the Node layout dependency in the project/workspace
npm install elkjs
```

For development, install the package in editable mode:

```bash
pip install -e ".[dev]"
npm install
```

Install KiCad separately if you want library search, KiCad file generation, or ERC:

```bash
# Ubuntu/Debian example
sudo apt update
sudo apt install kicad
```

### Windows

Install Python 3.11+, Node.js 18+, and KiCad first. Then run these commands from PowerShell in the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install .
npm install elkjs
```

For development:

```powershell
pip install -e ".[dev]"
npm install
```

If PowerShell blocks venv activation, run:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Optional HTTP Support

The default MCP transport is stdio and does not need HTTP dependencies. Install the HTTP extras only if you want to run the HTTP transport:

```bash
pip install ".[http]"
```

When CircuitWeaver is published to PyPI, the Python package can be installed with:

```bash
pip install circuitweaver
npm install elkjs
```

## Quick Start

The examples below assume `circuitweaver` is on your `PATH`. If you installed into a virtual environment and your MCP client is not launched from that activated shell, use the absolute executable path instead:

```bash
/path/to/circuitweaver/.venv/bin/circuitweaver serve
```

```powershell
C:\path\to\circuitweaver\.venv\Scripts\circuitweaver.exe serve
```

### Add to Claude Code

```bash
# Add CircuitWeaver as an MCP server
claude mcp add circuitweaver -- circuitweaver serve
```

### Add to Codex

```bash
codex mcp add circuitweaver -- circuitweaver serve
```

### Add to Gemini CLI

Add this to your Gemini CLI `settings.json`:

```json
{
  "mcpServers": {
    "circuitweaver": {
      "command": "circuitweaver",
      "args": ["serve"],
      "timeout": 30000
    }
  }
}
```

Once added, an MCP client can use CircuitWeaver tools to:
- Search KiCad part libraries
- Get component pinouts
- Validate Circuit JSON designs
- Create schematic layouts and KiCad files
- Run electrical rules checks

### Standalone CLI

```bash
# Validate a Circuit JSON file
circuitweaver validate design.json

# Compile to KiCad schematic
circuitweaver compile design.json -o output/

# Run ERC on generated schematic
circuitweaver erc output/project.kicad_sch

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

| Tool | Description | External requirements |
|------|-------------|-----------------------|
| `search_kicad_parts` | Search KiCad component libraries | KiCad libraries for full results |
| `get_symbol_pins` | Get pin positions for a symbol | KiCad libraries for custom symbols |
| `validate_circuit_json` | Validate Circuit JSON | None |
| `create_schematic` | Generate schematic layout and KiCad files | Node.js + `elkjs`; KiCad libraries for symbols |
| `run_erc` | Compile a Circuit JSON file and run ERC | Node.js + `elkjs` + `kicad-cli` |

The MCP server intentionally does not expose generic `read_file`, `write_file`, or `edit_file` tools. Claude Code, Codex, Gemini CLI, and similar clients already provide their own file operations.

## MCP Prompts and Resources

CircuitWeaver exposes one reusable prompt:

- `design-guidelines` - tells the client how to use CircuitWeaver resources and tools for circuit design.

MCP clients usually do not inject server prompts or resources into the model automatically. The client must select the prompt or read the resource. CircuitWeaver exposes these resources:

| Resource | Purpose |
|----------|---------|
| `circuitweaver://docs/readme` | Project overview and quick start |
| `circuitweaver://docs/install` | Linux, Windows, and optional HTTP install instructions |
| `circuitweaver://docs/mcp-workflow` | Recommended MCP design workflow |
| `circuitweaver://tools/reference` | Live tool reference generated from enabled tools |
| `circuitweaver://docs/circuit-json-spec` | Complete Circuit JSON specification |
| `circuitweaver://docs/troubleshooting` | Common setup and runtime issues |
| `circuitweaver://examples/simple-led` | Example logic-only Circuit JSON |

## Development

```bash
# Clone and install with dev dependencies
git clone https://github.com/yourusername/circuitweaver.git
cd circuitweaver
pip install -e ".[dev]"
npm install

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

Contributions are welcome. Please open an issue or pull request with a focused description of the change.

## Acknowledgments

- [KiCad](https://www.kicad.org/) - The open source EDA suite
- [Anthropic MCP](https://github.com/anthropics/mcp) - Model Context Protocol
- [tscircuit](https://github.com/tscircuit/tscircuit) - Inspiration for Circuit JSON format

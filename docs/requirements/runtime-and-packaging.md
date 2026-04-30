# Runtime and Packaging Requirements

## Package Metadata

- [implemented] `PKG-001` The Python package name shall be `circuitweaver`.
- [implemented] `PKG-002` The package version shall be exposed as `circuitweaver.__version__`.
- [implemented] `PKG-003` The package version in `pyproject.toml` and `circuitweaver.__version__` shall match.
- [implemented] `PKG-004` The package shall require Python `>=3.11`.
- [implemented] `PKG-005` The package shall expose a console script named `circuitweaver` mapped to `circuitweaver.cli:main`.
- [implemented] `PKG-006` The package shall be buildable with the Hatchling build backend.

## Python Dependencies

- [implemented] `PKG-010` Runtime Python dependencies shall include `mcp`, `pydantic`, `click`, `rich`, and `sexpdata`.
- [implemented] `PKG-011` Optional HTTP transport dependencies shall be installable through the `http` extra.
- [implemented] `PKG-012` The `http` extra shall include `fastapi`, `sse-starlette`, and `uvicorn[standard]`.
- [implemented] `PKG-013` Development dependencies shall be installable through the `dev` extra.
- [implemented] `PKG-014` Documentation dependencies shall be installable through the `docs` extra.
- [implemented] `PKG-015` The `all` extra shall include `http`, `dev`, and `docs` extras.

## Non-Python Runtime Dependencies

- [implemented] `PKG-020` Auto-layout shall require a `node` executable on `PATH`.
- [implemented] `PKG-021` Auto-layout shall require the Node package `elkjs`.
- [implemented] `PKG-022` The Node runtime dependency shall be declared in the repository-root `package.json`.
- [implemented] `PKG-023` KiCad library lookup shall use installed KiCad symbol libraries when available.
- [implemented] `PKG-024` KiCad ERC shall require a runnable `kicad-cli` command unless a different executable path is injected through `CompileEngine(kicad_cli_path=...)` or `ERCChecker(kicad_cli_path=...)`.

## Packaged Assets

- [implemented] `PKG-030` Built wheels shall include `circuitweaver/compiler/layout_helper.js`.
- [implemented] `PKG-031` Built wheels shall include `circuitweaver/README.md`.
- [implemented] `PKG-032` Built wheels shall include `circuitweaver/docs/circuit-json-spec.md`.
- [implemented] `PKG-033` Built wheels shall include `circuitweaver/docs/mcp-workflow.md`.
- [implemented] `PKG-034` Built wheels shall include `circuitweaver/docs/troubleshooting.md`.
- [implemented] `PKG-035` Built wheels shall include `circuitweaver/examples/simple_led/circuit.json`.

## Node Module Resolution

- [implemented] `PKG-040` Auto-layout shall run the packaged `layout_helper.js` with `node`.
- [implemented] `PKG-041` Auto-layout shall set `NODE_PATH` for the Node subprocess.
- [implemented] `PKG-042` `NODE_PATH` shall include the current working directory's `node_modules`.
- [implemented] `PKG-043` `NODE_PATH` shall include the repository-root `node_modules` when running from a source tree.
- [implemented] `PKG-044` Existing `NODE_PATH` values shall be preserved after CircuitWeaver-added paths.


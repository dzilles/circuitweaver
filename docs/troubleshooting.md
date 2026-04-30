# CircuitWeaver Troubleshooting

## `circuitweaver` Command Not Found

If CircuitWeaver was installed into a virtual environment, use the executable from that environment when configuring MCP clients:

```bash
/path/to/circuitweaver/.venv/bin/circuitweaver serve
```

On Windows:

```powershell
C:\path\to\circuitweaver\.venv\Scripts\circuitweaver.exe serve
```

## Node.js Not Found

`create_schematic` and `run_erc` need Node.js for auto-layout. Install Node.js 18 or newer and confirm it is on `PATH`:

```bash
node --version
```

## `Cannot find module 'elkjs'`

Install the Node layout dependency in the project or workspace where the MCP client runs:

```bash
npm install elkjs
```

If the MCP client starts CircuitWeaver from a different working directory, either run `npm install elkjs` there or set `NODE_PATH` to the directory containing `node_modules`.

## KiCad Or `kicad-cli` Not Found

KiCad is needed for full library lookup and ERC. Install KiCad 10 or newer and confirm the CLI is available:

```bash
kicad-cli --version
```

## MCP Prompt Does Not Appear Automatically

MCP prompts are exposed to clients, but clients usually do not inject them automatically. Select the `design-guidelines` prompt in the client if supported, or ask the client to read:

- `circuitweaver://docs/mcp-workflow`
- `circuitweaver://tools/reference`
- `circuitweaver://docs/circuit-json-spec`

## Tool Is Missing

The server can be started with `--tools` to enable only selected tools. Read `circuitweaver://tools/reference` to see which tools are active in the current session.

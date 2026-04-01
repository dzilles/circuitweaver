"""Command-line interface for CircuitWeaver."""

import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from circuitweaver import __version__

console = Console()
error_console = Console(stderr=True)


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="circuitweaver")
@click.pass_context
def main(ctx: click.Context) -> None:
    """CircuitWeaver - Generate KiCad schematics from Circuit JSON.

    An MCP server and CLI tool for AI-assisted electronic schematic design.
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.command()
@click.option(
    "--transport",
    type=click.Choice(["stdio", "http"]),
    default="stdio",
    help="Transport protocol for MCP server.",
)
@click.option(
    "--port",
    type=int,
    default=3000,
    help="Port for HTTP transport (ignored for stdio).",
)
@click.option(
    "--host",
    type=str,
    default="127.0.0.1",
    help="Host for HTTP transport (ignored for stdio).",
)
@click.option(
    "--tools",
    type=str,
    default=None,
    help="Comma-separated list of tools to enable (default: all).",
)
def serve(transport: str, port: int, host: str, tools: Optional[str]) -> None:
    """Start the MCP server.

    Examples:

        # Start with stdio transport (for Claude Code)
        circuitweaver serve

        # Start with HTTP transport
        circuitweaver serve --transport http --port 3000
    """
    from circuitweaver.server import create_server, run_server

    tool_list = tools.split(",") if tools else None
    server = create_server(enabled_tools=tool_list)

    if transport == "stdio":
        run_server(server, transport="stdio")
    else:
        console.print(f"[green]Starting CircuitWeaver MCP server on {host}:{port}...[/green]")
        run_server(server, transport="http", host=host, port=port)


@main.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format for validation results.",
)
def validate(input_file: Path, output_format: str) -> None:
    """Validate a Circuit JSON file.

    Checks for:
    - Integer coordinates (no floats)
    - Orthogonal traces (no diagonals)
    - Components within box bounds
    - Source-first rule compliance
    - Unique IDs
    - Hierarchy link consistency

    Example:

        circuitweaver validate design.json
    """
    from circuitweaver.validator import validate_circuit_file

    result = validate_circuit_file(input_file)

    if output_format == "json":
        import json

        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        if result.is_valid:
            console.print(f"[green]Valid[/green] {input_file}")
            if result.warnings:
                console.print(f"[yellow]Warnings: {len(result.warnings)}[/yellow]")
                for warning in result.warnings:
                    console.print(f"  - {warning}")
        else:
            error_console.print(f"[red]Invalid[/red] {input_file}")
            error_console.print(f"[red]Errors: {len(result.errors)}[/red]")
            for error in result.errors:
                error_console.print(f"  - {error}")
            sys.exit(1)


@main.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory (default: same as input file).",
)
@click.option(
    "--validate/--no-validate",
    default=True,
    help="Run validation before compilation.",
)
def compile(input_file: Path, output: Optional[Path], validate: bool) -> None:
    """Compile Circuit JSON to KiCad schematic.

    Generates .kicad_sch files from the Circuit JSON input.
    Requires KiCad 10.0+ to be installed.

    Example:

        circuitweaver compile design.json -o output/
    """
    from circuitweaver.compiler import compile_to_kicad
    from circuitweaver.validator import validate_circuit_file

    if validate:
        result = validate_circuit_file(input_file)
        if not result.is_valid:
            error_console.print("[red]Validation failed. Fix errors before compiling:[/red]")
            for error in result.errors:
                error_console.print(f"  - {error}")
            sys.exit(1)

    output_dir = output or input_file.parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        output_files = compile_to_kicad(input_file, output_dir)
        console.print("[green]Compilation successful![/green]")
        console.print("Generated files:")
        for f in output_files:
            console.print(f"  - {f}")
    except Exception as e:
        error_console.print(f"[red]Compilation failed: {e}[/red]")
        sys.exit(1)


@main.command()
@click.argument("schematic_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format for ERC results.",
)
def erc(schematic_file: Path, output_format: str) -> None:
    """Run Electrical Rules Check on a KiCad schematic.

    Requires KiCad 10.0+ with kicad-cli available in PATH.

    Example:

        circuitweaver erc output/main.kicad_sch
    """
    from circuitweaver.erc import run_erc

    result = run_erc(schematic_file)

    if output_format == "json":
        import json

        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        if result.passed:
            console.print(f"[green]ERC passed[/green] {schematic_file}")
            if result.warnings:
                console.print(f"[yellow]Warnings: {len(result.warnings)}[/yellow]")
                for warning in result.warnings:
                    console.print(f"  - {warning}")
        else:
            error_console.print(f"[red]ERC failed[/red] {schematic_file}")
            error_console.print(f"[red]Errors: {len(result.errors)}[/red]")
            for error in result.errors:
                error_console.print(f"  - {error}")
            sys.exit(1)


@main.command()
@click.argument("query", type=str)
@click.option(
    "--limit",
    type=int,
    default=10,
    help="Maximum number of results.",
)
def search(query: str, limit: int) -> None:
    """Search KiCad component libraries.

    Example:

        circuitweaver search "STM32G4"
        circuitweaver search "resistor 0603"
    """
    from circuitweaver.library import search_parts

    results = search_parts(query, limit=limit)

    if not results:
        console.print(f"[yellow]No results found for '{query}'[/yellow]")
        return

    table = Table(title=f"Search results for '{query}'")
    table.add_column("Library:Symbol", style="cyan")
    table.add_column("Description")
    table.add_column("Footprint", style="dim")

    for part in results:
        table.add_row(
            part.library_id,
            part.description or "",
            part.default_footprint or "",
        )

    console.print(table)


@main.command()
@click.argument("symbol_id", type=str)
def pinout(symbol_id: str) -> None:
    """Get pinout information for a KiCad symbol.

    Shows pin names, numbers, and positions in grid units.

    Example:

        circuitweaver pinout "Device:R"
        circuitweaver pinout "MCU_ST_STM32G4:STM32G431CBUx"
    """
    from circuitweaver.library import get_symbol_pinout

    try:
        pins = get_symbol_pinout(symbol_id)
    except ValueError as e:
        error_console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    table = Table(title=f"Pinout for {symbol_id}")
    table.add_column("Pin", style="cyan")
    table.add_column("Name")
    table.add_column("X", justify="right")
    table.add_column("Y", justify="right")
    table.add_column("Direction")
    table.add_column("Type")

    for pin in pins:
        table.add_row(
            str(pin.number),
            pin.name,
            str(pin.grid_offset.x),
            str(pin.grid_offset.y),
            pin.direction,
            pin.electrical_type,
        )

    console.print(table)


@main.command()
def info() -> None:
    """Show system information and dependencies."""
    import shutil

    table = Table(title="CircuitWeaver System Info")
    table.add_column("Component", style="cyan")
    table.add_column("Status")
    table.add_column("Details")

    # Python version
    table.add_row(
        "Python",
        "[green]OK[/green]",
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    )

    # CircuitWeaver version
    table.add_row("CircuitWeaver", "[green]OK[/green]", __version__)

    # KiCad CLI
    kicad_cli = shutil.which("kicad-cli")
    if kicad_cli:
        table.add_row("kicad-cli", "[green]OK[/green]", kicad_cli)
    else:
        table.add_row(
            "kicad-cli",
            "[yellow]Not found[/yellow]",
            "Required for compile/erc commands",
        )

    # KiCad libraries
    from circuitweaver.library import get_library_paths

    lib_paths = get_library_paths()
    if lib_paths.symbols:
        table.add_row("Symbol libraries", "[green]OK[/green]", str(lib_paths.symbols))
    else:
        table.add_row("Symbol libraries", "[yellow]Not found[/yellow]", "")

    if lib_paths.footprints:
        table.add_row("Footprint libraries", "[green]OK[/green]", str(lib_paths.footprints))
    else:
        table.add_row("Footprint libraries", "[yellow]Not found[/yellow]", "")

    console.print(table)


if __name__ == "__main__":
    main()

"""Command-line interface for CircuitWeaver."""

import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from circuitweaver import __version__
from circuitweaver.library.paths import get_library_paths

console = Console()
error_console = Console(stderr=True)


@click.group()
@click.version_option(version=__version__)
def main() -> None:
    """CircuitWeaver: Circuit JSON to KiCad compiler."""
    pass


@main.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output-format",
    "-f",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format for validation results.",
)
def validate(input_file: Path, output_format: str) -> None:
    """Validate a Circuit JSON file."""
    from circuitweaver.validator import validate_circuit_file

    result = validate_circuit_file(input_file)

    if output_format == "json":
        import json

        console.print(json.dumps(result.to_dict(), indent=2))
    else:
        if result.is_valid:
            console.print(f"[bold green]SUCCESS:[/bold green] {input_file} is valid.")
        else:
            error_console.print(
                f"[bold red]FAILED:[/bold red] {input_file} has {len(result.errors)} error(s)."
            )

        if result.errors:
            error_console.print("\n[bold red]Errors:[/bold red]")
            for error in result.errors:
                error_console.print(f"  - {error}")

        if result.warnings:
            console.print("\n[bold yellow]Warnings:[/bold yellow]")
            for warning in result.warnings:
                console.print(f"  - {warning}")

    if not result.is_valid:
        sys.exit(1)


@main.command()
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--output-dir", "-o", default="output", help="Directory where to save KiCad files")
@click.option("--name", "-n", default="project", help="Name of the KiCad project")
def compile(file_path: str, output_dir: str, name: str):
    """Compile Circuit JSON to KiCad schematic."""
    import json
    from pathlib import Path

    from pydantic import TypeAdapter
    from rich.progress import Progress, SpinnerColumn, TextColumn

    from circuitweaver.compiler.compiler import Compiler
    from circuitweaver.types.circuit_json import CircuitElement

    console.print(f"[bold blue]Compiling[/bold blue] {file_path}...")

    try:
        with open(file_path, "r") as f:
            data = json.load(f)

        adapter = TypeAdapter(list[CircuitElement])
        elements = adapter.validate_python(data)

        compiler = Compiler()
        out_path = Path(output_dir)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description="Running layout and writing KiCad files...", total=None)
            sch_file = compiler.compile(elements, out_path, project_name=name)

        console.print(f"\n[bold green]SUCCESS:[/bold green] Compiled to [cyan]{sch_file}[/cyan]")

    except Exception as e:
        console.print(f"\n[bold red]FAILED:[/bold red] {e}")
        import traceback
        error_console.print(traceback.format_exc())
        sys.exit(1)


@main.command()
@click.argument("schematic_path", type=click.Path(exists=True))
def erc(schematic_path: str):
    """Run KiCad Electrical Rules Check (ERC) on a schematic."""
    from pathlib import Path

    from circuitweaver.erc.checker import ERCChecker

    path = Path(schematic_path)
    console.print(f"[bold blue]Running ERC on[/bold blue] {schematic_path}...")

    checker = ERCChecker()
    try:
        result = checker.run(path)

        if result["is_valid"]:
            console.print("[bold green]ERC PASSED:[/bold green] No errors found.")
        else:
            console.print(f"[bold red]ERC FAILED:[/bold red] Found {len(result['errors'])} errors.")

        if result["errors"]:
            console.print("\n[bold red]Errors:[/bold red]")
            for err in result["errors"]:
                console.print(f"  - {err}")

        if result["warnings"]:
            console.print("\n[bold yellow]Warnings:[/bold yellow]")
            for warn in result["warnings"]:
                console.print(f"  - {warn}")

    except Exception as e:
        console.print(f"\n[bold red]FAILED to run ERC:[/bold red] {e}")
        sys.exit(1)


@main.command()
@click.argument("query", type=str)
@click.option(
    "--limit",
    type=int,
    default=10,
    help="Maximum number of results to return.",
)
def search(query: str, limit: int) -> None:
    """Search for KiCad parts by keyword."""
    from circuitweaver.library import search_parts

    results = search_parts(query, limit=limit)

    if not results:
        console.print(f"[yellow]No results found for '{query}'[/yellow]")
        return

    table = Table(title=f"Search results for '{query}'")
    table.add_column("Library ID", style="cyan")
    table.add_column("Description")

    for part in results:
        table.add_row(part.library_id, part.description)

    console.print(table)


@main.command()
@click.argument("symbol_id", type=str)
def pins(symbol_id: str) -> None:
    """Get pin information for a KiCad symbol."""
    from circuitweaver.library import get_symbol_pinout

    try:
        pin_list = get_symbol_pinout(symbol_id)
    except ValueError as e:
        error_console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)

    table = Table(title=f"Pins for {symbol_id}")
    table.add_column("Pin #", style="cyan")
    table.add_column("Name")
    table.add_column("Type")

    for pin in pin_list:
        table.add_row(
            str(pin.number),
            pin.name,
            pin.electrical_type,
        )

    console.print(table)


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
    default="localhost",
    help="Host for HTTP transport (ignored for stdio).",
)
def serve(transport: str, port: int, host: str) -> None:
    """Run the MCP server."""
    from circuitweaver.server.mcp_server import run_server

    console.print(f"[bold blue]Starting CircuitWeaver MCP server ({transport})...[/bold blue]")
    run_server(transport=transport, port=port, host=host)


@main.command()
def info() -> None:
    """Display information about the CircuitWeaver environment."""
    lib_paths = get_library_paths()

    table = Table(title="CircuitWeaver Information")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Details")

    table.add_row("Version", "[green]OK[/green]", __version__)

    if lib_paths.symbols.exists():
        table.add_row("Symbol libraries", "[green]OK[/green]", str(lib_paths.symbols))
    else:
        table.add_row("Symbol libraries", "[red]Not found[/red]", "")

    if lib_paths.footprints.exists():
        table.add_row("Footprint libraries", "[green]OK[/green]", str(lib_paths.footprints))
    else:
        table.add_row("Footprint libraries", "[yellow]Not found[/yellow]", "")

    console.print(table)


if __name__ == "__main__":
    main()

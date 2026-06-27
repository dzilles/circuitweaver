"""Compiler for Circuit JSON to KiCad schematic format."""

from circuitweaver.compiler.auto_router import AutoRouter
from circuitweaver.compiler.engine import CompileEngine


def compile_to_kicad(input_file, output_dir):
    """Simple wrapper for the CompileEngine class."""
    import json
    from pathlib import Path

    from circuitweaver.types import CircuitElement

    with open(input_file) as f:
        data = json.load(f)

    # Handle list or dict with 'elements' key
    if isinstance(data, dict) and "elements" in data:
        elements_data = data["elements"]
    elif isinstance(data, list):
        elements_data = data
    else:
        raise ValueError("Invalid circuit JSON format")

    from pydantic import TypeAdapter
    adapter = TypeAdapter(list[CircuitElement])
    elements = adapter.validate_python(elements_data)

    engine = CompileEngine()
    return engine.compile(elements, Path(output_dir), project_name=Path(input_file).stem)


__all__ = ["CompileEngine", "AutoRouter", "compile_to_kicad"]

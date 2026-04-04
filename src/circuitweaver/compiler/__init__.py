"""Compiler for Circuit JSON to KiCad schematic format."""

from circuitweaver.compiler.compiler import Compiler

def compile_to_kicad(input_file, output_dir):
    """Simple wrapper for the Compiler class."""
    import json
    from pathlib import Path
    from circuitweaver.types.circuit_json import CircuitElement
    
    with open(input_file, "r") as f:
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
    
    compiler = Compiler()
    return compiler.compile(elements, Path(output_dir), project_name=Path(input_file).stem)

__all__ = ["Compiler", "compile_to_kicad"]

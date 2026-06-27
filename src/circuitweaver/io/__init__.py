"""I/O modules for CircuitWeaver.

This package handles reading and writing files:
- json: JSON files for Source, Layout, and Schematic elements
- s_expr: S-expression files for KiCad schematics
"""

from circuitweaver.io.json import (
    # Type maps
    ELEMENT_TYPE_MAP,
    SCHEMATIC_TYPE_MAP,
    SOURCE_TYPE_MAP,
    describe_unknown_field,
    get_element_id_from_raw,
    get_unknown_fields,
    # Element parsing helpers
    parse_element,
    # Circuit (combined Source + Schematic)
    read_circuit,
    # Layout only
    read_layout,
    # Schematic only
    read_schematic,
    # Source only
    read_source,
    write_circuit,
    write_layout,
    write_schematic,
    write_source,
)
from circuitweaver.io.s_expr import (
    read_s_expr,
    write_s_expr,
)

__all__ = [
    # JSON I/O
    "read_circuit",
    "write_circuit",
    "read_source",
    "write_source",
    "read_layout",
    "write_layout",
    "read_schematic",
    "write_schematic",
    "ELEMENT_TYPE_MAP",
    "SOURCE_TYPE_MAP",
    "SCHEMATIC_TYPE_MAP",
    "parse_element",
    "get_element_id_from_raw",
    "get_unknown_fields",
    "describe_unknown_field",
    # S-expr I/O
    "read_s_expr",
    "write_s_expr",
]

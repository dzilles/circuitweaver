"""CircuitWeaver - MCP server for generating KiCad schematics from Circuit JSON."""

__version__ = "0.1.0"
__author__ = "CircuitWeaver Contributors"

from circuitweaver.types.circuit_json import (
    CircuitElement,
    SchematicBox,
    SchematicComponent,
    SchematicNetLabel,
    SchematicPort,
    SchematicSheet,
    SchematicText,
    SchematicTrace,
    SourceComponent,
    SourceNet,
    SourcePort,
    SourceTrace,
)

__all__ = [
    "__version__",
    # Source types
    "SourceComponent",
    "SourcePort",
    "SourceNet",
    "SourceTrace",
    # Schematic types
    "SchematicSheet",
    "SchematicComponent",
    "SchematicPort",
    "SchematicTrace",
    "SchematicBox",
    "SchematicNetLabel",
    "SchematicText",
    # Union type
    "CircuitElement",
]

"""Type definitions for CircuitWeaver."""

from circuitweaver.types.circuit_json import (
    CircuitElement,
    Point,
    SchematicBox,
    SchematicComponent,
    SchematicError,
    SchematicLine,
    SchematicNetLabel,
    SchematicPort,
    SchematicSheet,
    SchematicText,
    SchematicTrace,
    Size,
    SourceComponent,
    SourceNet,
    SourcePort,
    SourceTrace,
    TraceEdge,
)
from circuitweaver.types.errors import (
    CircuitWeaverError,
    CompilationError,
    ERCError,
    ValidationError,
)

__all__ = [
    # Primitives
    "Point",
    "Size",
    "TraceEdge",
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
    "SchematicLine",
    "SchematicError",
    # Union
    "CircuitElement",
    # Errors
    "CircuitWeaverError",
    "ValidationError",
    "CompilationError",
    "ERCError",
]

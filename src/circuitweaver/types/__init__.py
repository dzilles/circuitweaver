"""Type definitions for CircuitWeaver."""

from circuitweaver.types.circuit_json import (
    CircuitElement,
    Point,
    SchematicBox,
    SchematicComponent,
    SchematicHierarchicalLabel,
    SchematicHierarchicalPin,
    SchematicNetLabel,
    SchematicNoConnect,
    SchematicPort,
    SchematicText,
    SchematicTrace,
    SchematicTraceEdge,
    Size,
    SourceComponent,
    SourceGroup,
    SourceNet,
    SourcePort,
    SourceTrace,
    get_element_id,
    get_element_type,
)
from circuitweaver.types.errors import (
    CircuitWeaverError,
    CompilationError,
    ERCError,
    KiCadNotFoundError,
    ValidationError,
)

__all__ = [
    # Source types
    "SourceComponent",
    "SourcePort",
    "SourceNet",
    "SourceTrace",
    "SourceGroup",
    # Schematic types
    "SchematicComponent",
    "SchematicPort",
    "SchematicTrace",
    "SchematicTraceEdge",
    "SchematicBox",
    "SchematicNetLabel",
    "SchematicHierarchicalPin",
    "SchematicHierarchicalLabel",
    "SchematicText",
    "SchematicNoConnect",
    # Common
    "Point",
    "Size",
    # Union
    "CircuitElement",
    # Helpers
    "get_element_id",
    "get_element_type",
    # Errors
    "CircuitWeaverError",
    "ValidationError",
    "CompilationError",
    "ERCError",
    "KiCadNotFoundError",
]

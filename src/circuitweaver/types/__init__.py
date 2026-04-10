"""Type definitions for CircuitWeaver."""

from typing import Annotated, Union

from pydantic import Field

from circuitweaver.types.source import (
    LogicElement,
    SourceComponent,
    SourceGroup,
    SourceNet,
    SourcePort,
    SourceTrace,
)
from circuitweaver.types.schematic import (
    GridOffset,
    Point,
    SchematicBox,
    SchematicComponent,
    SchematicElement,
    SchematicElementBase,
    SchematicHierarchicalLabel,
    SchematicHierarchicalPin,
    SchematicNetLabel,
    SchematicNoConnect,
    SchematicPort,
    SchematicText,
    SchematicTrace,
    SchematicTraceEdge,
    Size,
)
from circuitweaver.types.layout import (
    LayoutEdge,
    LayoutEdgeSection,
    LayoutLabel,
    LayoutNode,
    LayoutPoint,
    LayoutPort,
)
from circuitweaver.types.s_expr import (
    ParseError as SExprParseError,
    RawString,
    SExpr,
    SExprValue,
    format_value as s_expr_format_value,
    parse as s_expr_parse,
    serialize as s_expr_serialize,
)
from circuitweaver.types.errors import (
    CircuitWeaverError,
    CompilationError,
    ERCError,
    KiCadNotFoundError,
    ValidationError,
)


# =============================================================================
# Union Type for All Elements
# =============================================================================

CircuitElement = Annotated[
    Union[
        SourceComponent,
        SourcePort,
        SourceNet,
        SourceTrace,
        SourceGroup,
        SchematicComponent,
        SchematicPort,
        SchematicTrace,
        SchematicBox,
        SchematicNetLabel,
        SchematicHierarchicalPin,
        SchematicHierarchicalLabel,
        SchematicText,
        SchematicNoConnect,
    ],
    Field(discriminator="type"),
]


# =============================================================================
# Helper functions
# =============================================================================


def get_element_id(element: CircuitElement) -> str:
    """Get the unique ID from any circuit element."""
    if isinstance(element, SourceComponent):
        return element.source_component_id
    elif isinstance(element, SourcePort):
        return element.source_port_id
    elif isinstance(element, SourceNet):
        return element.source_net_id
    elif isinstance(element, SourceTrace):
        return element.source_trace_id
    elif isinstance(element, SourceGroup):
        return element.source_group_id
    elif isinstance(element, SchematicComponent):
        return element.schematic_component_id
    elif isinstance(element, SchematicPort):
        return element.schematic_port_id
    elif isinstance(element, SchematicTrace):
        return element.schematic_trace_id
    elif isinstance(element, SchematicBox):
        return element.schematic_box_id
    elif isinstance(element, SchematicNetLabel):
        return element.schematic_net_label_id
    elif isinstance(element, SchematicHierarchicalPin):
        return element.schematic_hierarchical_pin_id
    elif isinstance(element, SchematicHierarchicalLabel):
        return element.schematic_hierarchical_label_id
    elif isinstance(element, SchematicText):
        return element.schematic_text_id
    elif isinstance(element, SchematicNoConnect):
        return element.schematic_no_connect_id
    else:
        raise ValueError(f"Unknown element type: {type(element)}")


def get_element_type(element: CircuitElement) -> str:
    """Get the type string from any circuit element."""
    return element.type


__all__ = [
    # Source types
    "SourceComponent",
    "SourcePort",
    "SourceNet",
    "SourceTrace",
    "SourceGroup",
    "LogicElement",
    # Layout types (ELK graph)
    "LayoutNode",
    "LayoutPort",
    "LayoutEdge",
    "LayoutEdgeSection",
    "LayoutPoint",
    "LayoutLabel",
    # Schematic types
    "SchematicElementBase",
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
    "SchematicElement",
    # S-expression types
    "SExpr",
    "RawString",
    "SExprValue",
    "SExprParseError",
    "s_expr_parse",
    "s_expr_serialize",
    "s_expr_format_value",
    # Common
    "Point",
    "Size",
    "GridOffset",
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

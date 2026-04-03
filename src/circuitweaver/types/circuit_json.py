"""Pydantic models for Circuit JSON format.

This module defines both logical source types and visual schematic types.

Source types (source_*) define WHAT is connected.
Schematic types (schematic_*) define WHERE things appear visually.

Types defined here follow the tscircuit circuit-json specification:
https://github.com/tscircuit/circuit-json
"""

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field


# =============================================================================
# Common Types
# =============================================================================


class Point(BaseModel):
    """X, Y coordinate pair."""

    x: float
    y: float


class Size(BaseModel):
    """Width, height pair."""

    width: float
    height: float


# =============================================================================
# Source Types (Logical/Netlist Layer)
# =============================================================================


class SourceComponent(BaseModel):
    """Logical part definition for BOM and netlist generation."""

    type: Literal["source_component"] = "source_component"
    source_component_id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Reference designator (R1, C1, U1)")

    # KiCad Symbol Mapping
    symbol_id: Optional[str] = Field(
        default=None,
        description="KiCad symbol ID (e.g., 'Device:R'). "
        "Required for validation and KiCad schematic generation.",
    )

    # Component subtype
    ftype: Optional[str] = Field(
        default=None,
        description="Component subtype: simple_resistor, simple_capacitor, etc.",
    )

    # Value fields
    resistance: Optional[float] = None
    capacitance: Optional[float] = None
    inductance: Optional[float] = None
    frequency: Optional[float] = None
    current_rating_amps: Optional[float] = None
    color: Optional[str] = None
    display_value: Optional[str] = None

    # PCB/BOM fields
    footprint: Optional[str] = None
    manufacturer_part_number: Optional[str] = None
    supplier_part_numbers: Optional[dict[str, list[str]]] = None

    # Hierarchy
    subcircuit_id: Optional[str] = Field(
        default=None, description="Subcircuit this component belongs to"
    )
    source_group_id: Optional[str] = Field(
        default=None, description="Parent group reference"
    )


class SourcePort(BaseModel):
    """Pin/terminal definition on a source component."""

    type: Literal["source_port"] = "source_port"
    source_port_id: str = Field(..., description="Unique identifier")
    source_component_id: str = Field(..., description="Parent component ID")
    name: str = Field(..., description="Pin name")
    pin_number: Optional[int] = None
    port_hints: Optional[list[str]] = None

    # Attributes
    is_power: Optional[bool] = None
    is_ground: Optional[bool] = None
    must_be_connected: Optional[bool] = None
    do_not_connect: Optional[bool] = None

    # Hierarchy
    subcircuit_id: Optional[str] = None


class SourceNet(BaseModel):
    """Named electrical signal definition."""

    type: Literal["source_net"] = "source_net"
    source_net_id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Net name")

    is_power: Optional[bool] = None
    is_ground: Optional[bool] = None
    is_digital_signal: Optional[bool] = None
    is_analog_signal: Optional[bool] = None
    trace_width: Optional[float] = None
    subcircuit_id: Optional[str] = None


class SourceTrace(BaseModel):
    """Logical connection between ports and/or nets."""

    type: Literal["source_trace"] = "source_trace"
    source_trace_id: str = Field(..., description="Unique identifier")

    connected_source_port_ids: list[str] = Field(..., description="Port IDs")
    connected_source_net_ids: list[str] = Field(default_factory=list)

    max_length: Optional[float] = None
    display_name: Optional[str] = None
    subcircuit_id: Optional[str] = None


class SourceGroup(BaseModel):
    """Hierarchical grouping for organizing complex designs."""

    type: Literal["source_group"] = "source_group"
    source_group_id: str = Field(..., description="Unique identifier")
    name: Optional[str] = None

    # Hierarchy
    subcircuit_id: Optional[str] = None
    parent_subcircuit_id: Optional[str] = None
    parent_source_group_id: Optional[str] = None
    is_subcircuit: Optional[bool] = Field(
        default=None, description="True if this is a separate schematic page (subcircuit)"
    )


# =============================================================================
# Schematic Types (Visual/Layout Layer)
# =============================================================================


class SchematicElementBase(BaseModel):
    """Base class for all schematic elements with sheet awareness."""

    sheet_id: str = Field(
        default="root", description="ID of the schematic sheet containing this element"
    )


class SchematicComponent(SchematicElementBase):
    """Visual placement of a component on the schematic."""

    type: Literal["schematic_component"] = "schematic_component"
    schematic_component_id: str = Field(..., description="Unique identifier")
    source_component_id: str = Field(..., description="Logical component reference")
    center: Point = Field(..., description="Center coordinate")
    rotation: float = Field(default=0, description="Rotation in degrees")
    symbol_name: Optional[str] = None


class SchematicPort(SchematicElementBase):
    """Connection point for a pin on the schematic."""

    type: Literal["schematic_port"] = "schematic_port"
    schematic_port_id: str = Field(..., description="Unique identifier")
    source_port_id: str = Field(..., description="Logical port reference")
    center: Point = Field(..., description="Coordinate")


class SchematicTraceEdge(BaseModel):
    """Single segment of a schematic trace."""

    from_: Point = Field(..., alias="from")
    to: Point


class SchematicTrace(SchematicElementBase):
    """Visual wire connecting ports on the schematic."""

    type: Literal["schematic_trace"] = "schematic_trace"
    schematic_trace_id: str = Field(..., description="Unique identifier")
    source_trace_id: Optional[str] = None
    edges: list[SchematicTraceEdge] = Field(..., description="Wire segments")


class SchematicBox(SchematicElementBase):
    """Visual box for grouping or hierarchical sheets."""

    type: Literal["schematic_box"] = "schematic_box"
    schematic_box_id: str = Field(..., description="Unique identifier")
    x: float
    y: float
    width: float
    height: float
    is_hierarchical_sheet: bool = Field(default=False)
    name: Optional[str] = None


class SchematicNetLabel(SchematicElementBase):
    """Visual net label on the schematic (local)."""

    type: Literal["schematic_net_label"] = "schematic_net_label"
    schematic_net_label_id: str = Field(..., description="Unique identifier")
    source_net_id: str = Field(..., description="Logical net reference")
    source_port_id: Optional[str] = Field(default=None, description="Port to snap to")
    center: Point = Field(..., description="Coordinate")
    text: str = Field(..., description="Label text")
    anchor_side: Literal["left", "right", "top", "bottom"] = "left"


class SchematicHierarchicalPin(SchematicElementBase):
    """Pin on a hierarchical sheet box (in the parent sheet)."""

    type: Literal["schematic_hierarchical_pin"] = "schematic_hierarchical_pin"
    schematic_hierarchical_pin_id: str = Field(..., description="Unique identifier")
    source_net_id: str = Field(..., description="Logical net reference")
    schematic_box_id: str = Field(..., description="Parent sheet box ID")
    center: Point = Field(..., description="Position on the box edge")
    text: str = Field(..., description="Pin name")


class SchematicHierarchicalLabel(SchematicElementBase):
    """Hierarchical label inside a sub-sheet."""

    type: Literal["schematic_hierarchical_label"] = "schematic_hierarchical_label"
    schematic_hierarchical_label_id: str = Field(..., description="Unique identifier")
    source_net_id: str = Field(..., description="Logical net reference")
    source_port_id: Optional[str] = Field(default=None, description="Port to snap to")
    center: Point = Field(..., description="Coordinate")
    text: str = Field(..., description="Label text")


class SchematicText(SchematicElementBase):
    """Visual text annotation."""

    type: Literal["schematic_text"] = "schematic_text"
    schematic_text_id: str = Field(..., description="Unique identifier")
    position: Point = Field(..., description="Coordinate")
    text: str = Field(..., description="The text content")
    rotation: float = Field(default=0, description="Rotation in degrees")


class SchematicNoConnect(SchematicElementBase):
    """Visual no-connect flag."""

    type: Literal["schematic_no_connect"] = "schematic_no_connect"
    schematic_no_connect_id: str = Field(..., description="Unique identifier")
    schematic_port_id: Optional[str] = None
    position: Optional[Point] = None


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

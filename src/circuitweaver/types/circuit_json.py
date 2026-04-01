"""Pydantic models for Circuit JSON format.

This module defines all the types used in the Circuit JSON specification.
Types are organized into two categories:

1. Source Types (Logical/BOM Layer):
   - SourceComponent: Logical part definition
   - SourcePort: Pin/terminal on a component
   - SourceNet: Named electrical net
   - SourceTrace: Logical connection between ports

2. Schematic Types (Visual/Layout Layer):
   - SchematicSheet: Sheet/page definition
   - SchematicComponent: Visual placement of a component
   - SchematicPort: Visual connection point
   - SchematicTrace: Wire connecting ports
   - SchematicBox: Visual grouping box
   - SchematicNetLabel: Net name label
   - SchematicText: Annotations and descriptions
   - SchematicLine: Decorative/grouping lines
   - SchematicError: Error marker
"""

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Primitive Types
# =============================================================================


class Point(BaseModel):
    """A point in 2D grid space.

    All coordinates are integers in fine grid units.
    1 grid unit = 0.127mm (5mil) for maximum precision with KiCad symbols.
    """

    model_config = ConfigDict(frozen=True)

    x: int = Field(..., description="X coordinate in grid units (0.127mm each)")
    y: int = Field(..., description="Y coordinate in grid units (0.127mm each)")


class Size(BaseModel):
    """Size dimensions in grid units."""

    model_config = ConfigDict(frozen=True)

    width: int = Field(..., ge=1, description="Width in grid units")
    height: int = Field(..., ge=1, description="Height in grid units")


class TraceEdge(BaseModel):
    """A single edge (segment) of a schematic trace.

    Each edge must be strictly orthogonal - either horizontal (same Y)
    or vertical (same X). Diagonal edges are not allowed.
    """

    model_config = ConfigDict(frozen=True)

    from_: Point = Field(..., alias="from", description="Start point of the edge")
    to: Point = Field(..., description="End point of the edge")
    from_schematic_port_id: Optional[str] = Field(
        default=None, description="Port ID at the start of this edge"
    )
    to_schematic_port_id: Optional[str] = Field(
        default=None, description="Port ID at the end of this edge"
    )

    def is_orthogonal(self) -> bool:
        """Check if this edge is strictly horizontal or vertical."""
        return self.from_.x == self.to.x or self.from_.y == self.to.y

    def is_horizontal(self) -> bool:
        """Check if this edge is horizontal."""
        return self.from_.y == self.to.y

    def is_vertical(self) -> bool:
        """Check if this edge is vertical."""
        return self.from_.x == self.to.x


# =============================================================================
# Port Arrangement Types
# =============================================================================


class PinArrangement(BaseModel):
    """Pin arrangement for one side of a component."""

    model_config = ConfigDict(frozen=True)

    pins: list[str] = Field(..., description="List of pin names on this side")
    direction: Optional[Literal["top-to-bottom", "bottom-to-top", "left-to-right", "right-to-left"]] = Field(
        default=None, description="Direction of pin ordering"
    )


class PortArrangement(BaseModel):
    """Port arrangement specification for box-style components."""

    model_config = ConfigDict(frozen=True)

    left_side: Optional[PinArrangement] = None
    right_side: Optional[PinArrangement] = None
    top_side: Optional[PinArrangement] = None
    bottom_side: Optional[PinArrangement] = None


# =============================================================================
# Source Types (Logical/BOM Layer)
# =============================================================================


class SourceComponent(BaseModel):
    """Logical part definition for BOM and netlist generation.

    This must be defined BEFORE any SchematicComponent that references it.
    """

    model_config = ConfigDict(frozen=True)

    type: Literal["source_component"] = "source_component"
    source_component_id: str = Field(
        ..., description="Unique identifier, referenced by schematic_component"
    )
    name: str = Field(..., description="Reference designator (R1, C1, U1)")
    value: Optional[str] = Field(
        default=None, description="Component value (10k, 100nF, STM32G431)"
    )
    footprint: Optional[str] = Field(
        default=None, description="KiCad footprint (Resistor_SMD:R_0603_1608Metric)"
    )
    supplier_part_numbers: Optional[dict[str, str]] = Field(
        default=None, description="Supplier part numbers, e.g., {'DigiKey': '123-ABC'}"
    )
    properties: Optional[dict[str, str]] = Field(
        default=None, description="Additional BOM fields"
    )


class SourcePort(BaseModel):
    """Pin/terminal definition on a source component."""

    model_config = ConfigDict(frozen=True)

    type: Literal["source_port"] = "source_port"
    source_port_id: str = Field(..., description="Unique identifier")
    source_component_id: str = Field(..., description="Parent component ID")
    name: str = Field(..., description="Pin name/number")
    pin_number: Optional[int] = Field(default=None, description="Physical pin number")
    port_hints: Optional[list[str]] = Field(
        default=None, description="Hints like ['left', 'right']"
    )


class SourceNet(BaseModel):
    """Named electrical net definition."""

    model_config = ConfigDict(frozen=True)

    type: Literal["source_net"] = "source_net"
    source_net_id: str = Field(
        ..., description="Unique identifier, referenced by schematic_net_label"
    )
    name: str = Field(..., description="Net name (VCC_3V3, GND, SPI_CLK)")
    member_source_port_ids: Optional[list[str]] = Field(
        default=None, description="Connected port IDs"
    )


class SourceTrace(BaseModel):
    """Logical connection between ports."""

    model_config = ConfigDict(frozen=True)

    type: Literal["source_trace"] = "source_trace"
    source_trace_id: str = Field(..., description="Unique identifier")
    connected_source_port_ids: list[str] = Field(
        ..., description="List of connected port IDs"
    )
    connected_source_net_ids: Optional[list[str]] = Field(
        default=None, description="Connected net IDs"
    )


# =============================================================================
# Schematic Types (Visual/Layout Layer)
# =============================================================================


class SchematicSheet(BaseModel):
    """Sheet/page definition in the schematic hierarchy."""

    model_config = ConfigDict(frozen=True)

    type: Literal["schematic_sheet"] = "schematic_sheet"
    schematic_sheet_id: str = Field(..., description="Unique identifier")
    name: Optional[str] = Field(default=None, description="Sheet name")
    subcircuit_id: Optional[str] = Field(
        default=None, description="Subcircuit identifier for hierarchy"
    )


class SchematicComponent(BaseModel):
    """Visual placement of a component on a schematic sheet."""

    model_config = ConfigDict(frozen=True)

    type: Literal["schematic_component"] = "schematic_component"
    schematic_component_id: str = Field(..., description="Unique identifier")
    source_component_id: str = Field(
        ..., description="Reference to source_component (MUST exist first)"
    )
    center: Point = Field(..., description="Center position in grid units")
    size: Optional[Size] = Field(default=None, description="Component size in grid units")
    rotation: int = Field(
        default=0, ge=0, lt=360, description="Rotation in degrees (0, 90, 180, 270)"
    )
    symbol_name: Optional[str] = Field(default=None, description="KiCad symbol name")
    is_box_with_pins: Optional[bool] = Field(
        default=None, description="Whether to render as a box with pins"
    )
    port_arrangement: Optional[PortArrangement] = Field(
        default=None, description="Pin arrangement for box-style components"
    )
    port_labels: Optional[dict[str, str]] = Field(
        default=None, description="Pin label overrides"
    )
    pin_spacing: Optional[int] = Field(
        default=None, description="Pin spacing in grid units"
    )
    box_width: Optional[int] = Field(
        default=None, description="Box width for box-style components"
    )


class SchematicPort(BaseModel):
    """Visual connection point on a schematic component."""

    model_config = ConfigDict(frozen=True)

    type: Literal["schematic_port"] = "schematic_port"
    schematic_port_id: str = Field(..., description="Unique identifier")
    source_port_id: str = Field(..., description="Reference to source_port")
    schematic_component_id: Optional[str] = Field(
        default=None, description="Parent component ID"
    )
    center: Point = Field(..., description="Port position in grid units")
    facing_direction: Optional[Literal["up", "down", "left", "right"]] = Field(
        default=None, description="Direction the port faces"
    )


class SchematicTrace(BaseModel):
    """Wire connecting ports via orthogonal edges."""

    model_config = ConfigDict(frozen=True)

    type: Literal["schematic_trace"] = "schematic_trace"
    schematic_trace_id: str = Field(..., description="Unique identifier")
    source_trace_id: Optional[str] = Field(
        default=None, description="Reference to source_trace"
    )
    subcircuit_connectivity_map_key: Optional[str] = Field(
        default=None, description="Hierarchical connection key (<subcircuit>.<net>)"
    )
    edges: list[TraceEdge] = Field(..., min_length=1, description="List of trace edges")

    def all_edges_orthogonal(self) -> bool:
        """Check if all edges in this trace are orthogonal."""
        return all(edge.is_orthogonal() for edge in self.edges)


class SchematicBox(BaseModel):
    """Visual grouping box for organizing components."""

    model_config = ConfigDict(frozen=True)

    type: Literal["schematic_box"] = "schematic_box"
    schematic_box_id: str = Field(..., description="Unique identifier")
    x: int = Field(..., description="Top-left X in grid units")
    y: int = Field(..., description="Top-left Y in grid units")
    width: int = Field(..., ge=1, description="Width in grid units")
    height: int = Field(..., ge=1, description="Height in grid units")


class SchematicNetLabel(BaseModel):
    """Net name label at trace endpoints."""

    model_config = ConfigDict(frozen=True)

    type: Literal["schematic_net_label"] = "schematic_net_label"
    source_net_id: str = Field(..., description="Reference to source_net")
    center: Point = Field(..., description="Label position in grid units")
    anchor_side: Literal["top", "bottom", "left", "right"] = Field(
        ..., description="Side where the label anchors to the wire"
    )
    text: str = Field(..., description="Label text (net name)")


class SchematicText(BaseModel):
    """Text annotation on the schematic."""

    model_config = ConfigDict(frozen=True)

    type: Literal["schematic_text"] = "schematic_text"
    schematic_text_id: str = Field(..., description="Unique identifier")
    schematic_box_id: Optional[str] = Field(
        default=None, description="Parent box ID (for text inside subgroup boxes)"
    )
    schematic_component_id: Optional[str] = Field(
        default=None, description="Parent component ID (for component labels)"
    )
    text: str = Field(..., description="Text content (supports newlines)")
    position: Point = Field(..., description="Text position in grid units")
    rotation: int = Field(default=0, ge=0, lt=360, description="Rotation in degrees")
    anchor: Literal["center", "left", "right", "top", "bottom"] = Field(
        default="left", description="Text anchor point"
    )


class SchematicLine(BaseModel):
    """Decorative or grouping line on the schematic."""

    model_config = ConfigDict(frozen=True)

    type: Literal["schematic_line"] = "schematic_line"
    schematic_line_id: str = Field(..., description="Unique identifier")
    schematic_box_id: Optional[str] = Field(
        default=None, description="Parent box ID"
    )
    schematic_component_id: Optional[str] = Field(
        default=None, description="Parent component ID"
    )
    x1: int = Field(..., description="Start X in grid units")
    y1: int = Field(..., description="Start Y in grid units")
    x2: int = Field(..., description="End X in grid units")
    y2: int = Field(..., description="End Y in grid units")


class SchematicError(BaseModel):
    """Error marker for invalid or missing elements."""

    model_config = ConfigDict(frozen=True)

    type: Literal["schematic_error"] = "schematic_error"
    schematic_error_id: str = Field(..., description="Unique identifier")
    error_type: Literal["schematic_port_not_found"] = Field(
        ..., description="Type of error"
    )
    message: str = Field(..., description="Error message")


class SchematicNoConnect(BaseModel):
    """No-connect flag for intentionally unconnected pins.

    Place this at the position of a pin that should not be connected.
    This prevents ERC errors for floating pins.
    """

    model_config = ConfigDict(frozen=True)

    type: Literal["schematic_no_connect"] = "schematic_no_connect"
    schematic_no_connect_id: str = Field(..., description="Unique identifier")
    schematic_port_id: str = Field(
        ..., description="Reference to the schematic_port this no-connect is attached to"
    )
    position: Point = Field(..., description="Position in grid units (must match port position)")


# =============================================================================
# Union Type for All Elements
# =============================================================================

CircuitElement = Annotated[
    Union[
        # Source types
        SourceComponent,
        SourcePort,
        SourceNet,
        SourceTrace,
        # Schematic types
        SchematicSheet,
        SchematicComponent,
        SchematicPort,
        SchematicTrace,
        SchematicBox,
        SchematicNetLabel,
        SchematicText,
        SchematicLine,
        SchematicError,
        SchematicNoConnect,
    ],
    Field(discriminator="type"),
]


# =============================================================================
# Circuit Document
# =============================================================================


class CircuitDocument(BaseModel):
    """A complete Circuit JSON document.

    This is the root type that contains all circuit elements.
    """

    model_config = ConfigDict(frozen=True)

    elements: list[CircuitElement] = Field(
        ..., description="All circuit elements (source and schematic types)"
    )

    def get_source_components(self) -> list[SourceComponent]:
        """Get all source components."""
        return [e for e in self.elements if isinstance(e, SourceComponent)]

    def get_schematic_components(self) -> list[SchematicComponent]:
        """Get all schematic components."""
        return [e for e in self.elements if isinstance(e, SchematicComponent)]

    def get_traces(self) -> list[SchematicTrace]:
        """Get all schematic traces."""
        return [e for e in self.elements if isinstance(e, SchematicTrace)]

    def get_sheets(self) -> list[SchematicSheet]:
        """Get all schematic sheets."""
        return [e for e in self.elements if isinstance(e, SchematicSheet)]

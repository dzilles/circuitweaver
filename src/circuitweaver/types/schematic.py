"""Pydantic models for the Visual (Schematic) layer of Circuit JSON.

This module defines WHERE things appear visually (positions, traces, labels).
The auto-layout engine generates these elements from the logical source layer.
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


class GridOffset(BaseModel):
    """X, Y offset in grid units."""

    x: int
    y: int


class Size(BaseModel):
    """Width, height pair."""

    width: float
    height: float


# =============================================================================
# Schematic Types (Visual/Layout Layer)
# =============================================================================


class SchematicElementBase(BaseModel):
    """Base class for all schematic elements with sheet awareness."""

    sheet_id: str = Field(
        ...,
        description="ID of the schematic sheet containing this element (required, no default)",
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
    child_sheet_id: Optional[str] = None
    name: Optional[str] = None

    # Offsets for Sheetname and Sheetfile properties relative to (x, y)
    name_offset: Point = Field(default_factory=lambda: Point(x=0, y=-10))
    file_offset: Point = Field(default_factory=lambda: Point(x=0, y=10))


class SchematicNetLabel(SchematicElementBase):
    """Visual net label on the schematic (local)."""

    type: Literal["schematic_net_label"] = "schematic_net_label"
    schematic_net_label_id: str = Field(..., description="Unique identifier")
    source_net_id: str = Field(..., description="Logical net reference")
    source_port_id: Optional[str] = Field(default=None, description="Port to snap to")
    schematic_hierarchical_pin_id: Optional[str] = Field(
        default=None, description="H-Pin to snap to"
    )
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
    anchor_side: Literal["left", "right", "top", "bottom"] = "left"


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
# Union Type for Schematic Elements
# =============================================================================

SchematicElement = Annotated[
    Union[
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

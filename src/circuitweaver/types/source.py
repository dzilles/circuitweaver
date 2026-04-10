"""Pydantic models for the Logical (Source) layer of Circuit JSON.

This module defines WHAT is connected (components, ports, nets, traces).
These models are strictly frozen (immutable) to prevent accidental state
mutations during validation and layout phases.
"""

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field


class SourceComponent(BaseModel):
    """Logical part definition for BOM and netlist generation."""

    model_config = {"frozen": True}

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

    model_config = {"frozen": True}

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

    model_config = {"frozen": True}

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

    model_config = {"frozen": True}

    type: Literal["source_trace"] = "source_trace"
    source_trace_id: str = Field(..., description="Unique identifier")

    connected_source_port_ids: list[str] = Field(..., description="Port IDs")
    connected_source_net_ids: list[str] = Field(default_factory=list)

    max_length: Optional[float] = None
    display_name: Optional[str] = None
    subcircuit_id: Optional[str] = None


class SourceGroup(BaseModel):
    """Hierarchical grouping for organizing complex designs."""

    model_config = {"frozen": True}

    type: Literal["source_group"] = "source_group"
    source_group_id: str = Field(..., description="Unique identifier")
    name: Optional[str] = None

    # Hierarchy
    subcircuit_id: Optional[str] = None
    parent_subcircuit_id: Optional[str] = None
    parent_source_group_id: Optional[str] = None
    is_subcircuit: Optional[bool] = Field(
        default=None,
        description="True if this is a separate schematic page (subcircuit)",
    )


# =============================================================================
# Union Type for Logical Elements
# =============================================================================

LogicElement = Annotated[
    Union[
        SourceComponent,
        SourcePort,
        SourceNet,
        SourceTrace,
        SourceGroup,
    ],
    Field(discriminator="type"),
]

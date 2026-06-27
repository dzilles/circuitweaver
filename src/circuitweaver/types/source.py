"""Pydantic models for the Logical (Source) layer of Circuit JSON.

This module defines WHAT is connected (components, ports, nets, traces).
These models are strictly frozen (immutable) to prevent accidental state
mutations during validation and layout phases.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class SourceComponent(BaseModel):
    """Logical part definition for BOM and netlist generation."""

    model_config = {"frozen": True}

    type: Literal["source_component"] = "source_component"
    source_component_id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Reference designator (R1, C1, U1)")

    # KiCad Symbol Mapping
    symbol_id: str | None = Field(
        default=None,
        description="KiCad symbol ID (e.g., 'Device:R'). "
        "Required for validation and KiCad schematic generation.",
    )

    # Component subtype
    ftype: str | None = Field(
        default=None,
        description="Component subtype: simple_resistor, simple_capacitor, etc.",
    )

    # Value fields
    resistance: float | None = None
    capacitance: float | None = None
    inductance: float | None = None
    frequency: float | None = None
    current_rating_amps: float | None = None
    color: str | None = None
    display_value: str | None = None

    # PCB/BOM fields
    footprint: str | None = None
    manufacturer_part_number: str | None = None
    supplier_part_numbers: dict[str, list[str]] | None = None

    # Hierarchy
    subcircuit_id: str | None = Field(
        default=None, description="Subcircuit this component belongs to"
    )
    source_group_id: str | None = Field(
        default=None, description="Parent group reference"
    )


class SourcePort(BaseModel):
    """Pin/terminal definition on a source component."""

    model_config = {"frozen": True}

    type: Literal["source_port"] = "source_port"
    source_port_id: str = Field(..., description="Unique identifier")
    source_component_id: str = Field(..., description="Parent component ID")
    name: str = Field(..., description="Pin name")
    pin_number: int | None = None
    port_hints: list[str] | None = None

    # Attributes
    is_power: bool | None = None
    is_ground: bool | None = None
    must_be_connected: bool | None = None
    do_not_connect: bool | None = None

    # Hierarchy
    subcircuit_id: str | None = None


class SourceNet(BaseModel):
    """Named electrical signal definition."""

    model_config = {"frozen": True}

    type: Literal["source_net"] = "source_net"
    source_net_id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Net name")

    is_power: bool | None = None
    is_ground: bool | None = None
    is_global: bool | None = None
    is_digital_signal: bool | None = None
    is_analog_signal: bool | None = None
    trace_width: float | None = None
    subcircuit_id: str | None = None


class SourceProjectConfig(BaseModel):
    """Project-level source settings."""

    model_config = {"frozen": True}

    type: Literal["source_project_config"] = "source_project_config"
    source_project_config_id: str = "project_config"
    global_net_names: list[str] = Field(default_factory=list)
    use_kicad_power_symbols_as_global_nets: bool = True


class SourceTrace(BaseModel):
    """Logical connection between ports and/or nets."""

    model_config = {"frozen": True}

    type: Literal["source_trace"] = "source_trace"
    source_trace_id: str = Field(..., description="Unique identifier")

    connected_source_port_ids: list[str] = Field(..., description="Port IDs")
    connected_source_net_ids: list[str] = Field(default_factory=list)

    max_length: float | None = None
    display_name: str | None = None
    subcircuit_id: str | None = None


class SourceGroup(BaseModel):
    """Hierarchical grouping for organizing complex designs."""

    model_config = {"frozen": True}

    type: Literal["source_group"] = "source_group"
    source_group_id: str = Field(..., description="Unique identifier")
    name: str | None = None

    # Hierarchy
    subcircuit_id: str | None = None
    parent_subcircuit_id: str | None = None
    parent_source_group_id: str | None = None
    is_subcircuit: bool | None = Field(
        default=None,
        description="True if this is a separate schematic page (subcircuit)",
    )


# =============================================================================
# Union Type for Logical Elements
# =============================================================================

LogicElement = Annotated[
    SourceComponent | SourcePort | SourceNet | SourceProjectConfig | SourceTrace | SourceGroup,
    Field(discriminator="type"),
]

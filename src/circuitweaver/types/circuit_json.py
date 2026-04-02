"""Pydantic models for Circuit JSON format.

This module defines the source types for the logical netlist layer.
These types are what the LLM generates - they define WHAT is connected,
not WHERE things appear visually.

Visual/layout types (schematic_*) will be added by the auto-layout tool
in Phase 2.

Types defined here follow the tscircuit circuit-json specification:
https://github.com/tscircuit/circuit-json
"""

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Source Types (Logical/Netlist Layer)
# =============================================================================


class SourceComponent(BaseModel):
    """Logical part definition for BOM and netlist generation.

    Represents a physical component that will appear in the design.
    Use `ftype` to specify the component subtype for better validation
    and auto-layout hints.
    """

    model_config = ConfigDict(frozen=True)

    type: Literal["source_component"] = "source_component"
    source_component_id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Reference designator (R1, C1, U1)")

    # KiCad Symbol Mapping
    symbol_id: Optional[str] = Field(
        default=None,
        description="KiCad symbol ID (e.g., 'Device:R'). "
        "Required for validation and KiCad schematic generation.",
    )

    # Component subtype (optional but recommended)
    ftype: Optional[str] = Field(
        default=None,
        description="Component subtype: simple_resistor, simple_capacitor, simple_inductor, "
        "simple_diode, simple_led, simple_chip, simple_crystal, simple_fuse, etc.",
    )

    # Value fields (use appropriate one based on ftype)
    resistance: Optional[float] = Field(
        default=None, description="Resistance in Ohms (for simple_resistor)"
    )
    capacitance: Optional[float] = Field(
        default=None, description="Capacitance in Farads (for simple_capacitor)"
    )
    inductance: Optional[float] = Field(
        default=None, description="Inductance in Henries (for simple_inductor)"
    )
    frequency: Optional[float] = Field(
        default=None, description="Frequency in Hz (for simple_crystal)"
    )
    current_rating_amps: Optional[float] = Field(
        default=None, description="Current rating in Amps (for simple_fuse)"
    )
    color: Optional[str] = Field(
        default=None, description="LED color (for simple_led)"
    )

    # Human-readable value (for display)
    display_value: Optional[str] = Field(
        default=None, description="Human-readable value string (e.g., '10k', '100nF')"
    )

    # PCB/BOM fields
    footprint: Optional[str] = Field(
        default=None,
        description="KiCad footprint (e.g., Resistor_SMD:R_0603_1608Metric). "
        "Leave blank if unsure - user can assign later.",
    )
    manufacturer_part_number: Optional[str] = Field(
        default=None, description="Manufacturer part number for BOM"
    )
    supplier_part_numbers: Optional[dict[str, list[str]]] = Field(
        default=None,
        description="Supplier part numbers, e.g., {'DigiKey': ['123-ABC']}",
    )

    # Hierarchy
    subcircuit_id: Optional[str] = Field(
        default=None, description="Subcircuit this component belongs to"
    )
    source_group_id: Optional[str] = Field(
        default=None, description="Parent group reference"
    )


class SourcePort(BaseModel):
    """Pin/terminal definition on a source component.

    Every pin that needs to be connected must have a SourcePort defined.
    Use get_symbol_pins tool to look up pin information for KiCad symbols.
    """

    model_config = ConfigDict(frozen=True)

    type: Literal["source_port"] = "source_port"
    source_port_id: str = Field(..., description="Unique identifier")
    source_component_id: str = Field(..., description="Parent component ID")
    name: str = Field(..., description="Pin name (e.g., 'VCC', 'GND', 'PA0', or '1')")
    pin_number: Optional[int] = Field(
        default=None, description="Physical pin number"
    )
    port_hints: Optional[list[str]] = Field(
        default=None, description="Layout hints like ['left', 'right', 'power']"
    )

    # Pin attributes (for validation and ERC)
    is_power: Optional[bool] = Field(
        default=None, description="True if this is a power pin"
    )
    is_ground: Optional[bool] = Field(
        default=None, description="True if this is a ground pin"
    )
    must_be_connected: Optional[bool] = Field(
        default=None, description="True if this pin must be connected (error if floating)"
    )
    do_not_connect: Optional[bool] = Field(
        default=None, description="True if this is a no-connect pin"
    )

    # Hierarchy
    subcircuit_id: Optional[str] = Field(
        default=None, description="Subcircuit this port belongs to"
    )


class SourceNet(BaseModel):
    """Named electrical signal definition.

    Nets are named signals that can span multiple traces.
    Use nets for power rails, ground, and named signals like I2C_SDA.
    """

    model_config = ConfigDict(frozen=True)

    type: Literal["source_net"] = "source_net"
    source_net_id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Net name (e.g., 'VCC_3V3', 'GND', 'I2C_SDA')")

    # Net attributes
    is_power: Optional[bool] = Field(
        default=None, description="True if this is a power net"
    )
    is_ground: Optional[bool] = Field(
        default=None, description="True if this is a ground net"
    )
    is_digital_signal: Optional[bool] = Field(
        default=None, description="True if this is a digital signal"
    )
    is_analog_signal: Optional[bool] = Field(
        default=None, description="True if this is an analog signal"
    )

    # PCB hints
    trace_width: Optional[float] = Field(
        default=None, description="Preferred trace width in mm"
    )

    # Hierarchy
    subcircuit_id: Optional[str] = Field(
        default=None, description="Subcircuit this net belongs to"
    )


class SourceTrace(BaseModel):
    """Logical connection between ports and/or nets.

    A trace connects multiple ports together, optionally associating
    them with a named net. This defines the netlist connectivity.
    """

    model_config = ConfigDict(frozen=True)

    type: Literal["source_trace"] = "source_trace"
    source_trace_id: str = Field(..., description="Unique identifier")

    # Connections (at least one port required)
    connected_source_port_ids: list[str] = Field(
        ..., description="List of port IDs to connect together"
    )
    connected_source_net_ids: list[str] = Field(
        default_factory=list,
        description="List of net IDs this trace belongs to (optional)",
    )

    # PCB hints
    max_length: Optional[float] = Field(
        default=None, description="Maximum trace length in mm"
    )

    # Display
    display_name: Optional[str] = Field(
        default=None, description="Display name for this connection"
    )

    # Hierarchy
    subcircuit_id: Optional[str] = Field(
        default=None, description="Subcircuit this trace belongs to"
    )


class SourceGroup(BaseModel):
    """Hierarchical grouping for organizing complex designs.

    Groups allow you to organize components into logical subcircuits.
    Components belong to a group by setting their subcircuit_id to
    match the group's subcircuit_id.
    """

    model_config = ConfigDict(frozen=True)

    type: Literal["source_group"] = "source_group"
    source_group_id: str = Field(..., description="Unique identifier")
    name: Optional[str] = Field(
        default=None, description="Display name for the group"
    )

    # Hierarchy
    subcircuit_id: Optional[str] = Field(
        default=None, description="ID used by child elements to declare membership"
    )
    parent_subcircuit_id: Optional[str] = Field(
        default=None, description="Parent subcircuit (for nested groups)"
    )
    parent_source_group_id: Optional[str] = Field(
        default=None, description="Parent group ID (for nested groups)"
    )
    is_subcircuit: Optional[bool] = Field(
        default=None, description="True if this is a reusable subcircuit"
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
    else:
        raise ValueError(f"Unknown element type: {type(element)}")


def get_element_type(element: CircuitElement) -> str:
    """Get the type string from any circuit element."""
    return element.type

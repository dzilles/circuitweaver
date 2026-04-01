"""Validation rule for unconnected pins."""

import logging
from typing import Any, Dict, Set

from circuitweaver.types.circuit_json import (
    CircuitElement,
    SchematicComponent,
    SchematicNoConnect,
    SchematicPort,
    SchematicTrace,
)
from circuitweaver.validator.result import ValidationResult
from circuitweaver.validator.rules.base import ValidationRule

logger = logging.getLogger(__name__)


class UnconnectedPinsRule(ValidationRule):
    """Ensure all pins are defined and connected or marked with no-connect.

    This rule enforces two requirements:
    1. Every pin on every component MUST have a schematic_port defined
    2. Every schematic_port must either be connected via a trace OR have a no-connect flag

    This prevents floating pin errors in the final schematic.
    """

    @property
    def name(self) -> str:
        return "unconnected_pins"

    @property
    def description(self) -> str:
        return "All pins must be defined as ports and either connected or marked with no-connect"

    def validate(
        self,
        elements: list[CircuitElement],
        context: dict[str, Any],
    ) -> ValidationResult:
        result = ValidationResult()

        # Collect all schematic ports, indexed by component
        all_ports: Dict[str, SchematicPort] = {}
        ports_by_component: Dict[str, Dict[str, SchematicPort]] = {}  # comp_id -> {pin_name -> port}
        port_to_component: Dict[str, str] = {}

        # Collect connected ports (from traces)
        connected_ports: Set[str] = set()

        # Collect no-connect ports
        no_connect_ports: Set[str] = set()

        # Component info
        components: Dict[str, SchematicComponent] = context.get("schematic_components", {})

        for element in elements:
            if isinstance(element, SchematicPort):
                all_ports[element.schematic_port_id] = element
                if element.schematic_component_id:
                    port_to_component[element.schematic_port_id] = element.schematic_component_id
                    # Index by component and pin name
                    if element.schematic_component_id not in ports_by_component:
                        ports_by_component[element.schematic_component_id] = {}
                    ports_by_component[element.schematic_component_id][element.source_port_id] = element

            elif isinstance(element, SchematicTrace):
                for edge in element.edges:
                    if edge.from_schematic_port_id:
                        connected_ports.add(edge.from_schematic_port_id)
                    if edge.to_schematic_port_id:
                        connected_ports.add(edge.to_schematic_port_id)

            elif isinstance(element, SchematicNoConnect):
                no_connect_ports.add(element.schematic_port_id)

        # PHASE 1: Check that all pins from symbol are defined as ports
        try:
            from circuitweaver.library.pinout import get_symbol_pinout
        except ImportError:
            logger.warning("Could not import pinout module, skipping pin definition check")
            get_symbol_pinout = None

        if get_symbol_pinout:
            for comp_id, comp in components.items():
                # Skip hierarchy blocks
                if comp.source_component_id.startswith("hierarchy:"):
                    continue

                # Get symbol ID
                symbol_id = comp.symbol_name if comp.symbol_name and ":" in comp.symbol_name else comp.source_component_id
                if ":" not in symbol_id:
                    continue

                try:
                    pins = get_symbol_pinout(symbol_id)
                except ValueError as e:
                    # Symbol not found - already reported by PinPositionsRule
                    logger.debug(f"Could not get pinout for {symbol_id}: {e}")
                    continue

                # Check each pin has a port defined
                comp_ports = ports_by_component.get(comp_id, {})
                for pin in pins:
                    if pin.number not in comp_ports and pin.name not in comp_ports:
                        result.add_error(
                            self.name,
                            f"Pin '{pin.number}' ({pin.name}) on component '{comp.source_component_id}' "
                            f"has no schematic_port defined. You MUST define a schematic_port for every pin. "
                            f"Example port definition:\n"
                            f'{{\n'
                            f'  "type": "schematic_port",\n'
                            f'  "schematic_port_id": "port_{comp_id}_{pin.number}",\n'
                            f'  "source_port_id": "{pin.number}",\n'
                            f'  "schematic_component_id": "{comp_id}",\n'
                            f'  "center": {{ "x": <calculate_from_component_center>, "y": <calculate_from_pin_offset> }},\n'
                            f'  "facing_direction": "{pin.direction}"\n'
                            f'}}',
                            element_id=comp_id,
                            location={
                                "component": comp.source_component_id,
                                "pin_number": pin.number,
                                "pin_name": pin.name,
                            },
                        )

        # PHASE 2: Check that all defined ports are connected or have no-connect
        for port_id, port in all_ports.items():
            if port_id in connected_ports:
                continue
            if port_id in no_connect_ports:
                continue

            # This port is neither connected nor marked with no-connect
            comp_id = port_to_component.get(port_id, "unknown")
            comp = components.get(comp_id)
            comp_name = comp.source_component_id if comp else comp_id

            result.add_error(
                self.name,
                f"Pin '{port.source_port_id}' on component '{comp_name}' is not connected. "
                f"Either connect it with a schematic_trace or add a schematic_no_connect flag. "
                f"Example no-connect in JSON:\n"
                f'{{\n'
                f'  "type": "schematic_no_connect",\n'
                f'  "schematic_no_connect_id": "nc_{port_id}",\n'
                f'  "schematic_port_id": "{port_id}",\n'
                f'  "position": {{ "x": {port.center.x}, "y": {port.center.y} }}\n'
                f'}}',
                element_id=port_id,
                location={
                    "x": port.center.x,
                    "y": port.center.y,
                    "component": comp_name,
                    "pin": port.source_port_id,
                },
            )

        # PHASE 3: Validate no-connect references exist
        for element in elements:
            if isinstance(element, SchematicNoConnect):
                if element.schematic_port_id not in all_ports:
                    result.add_error(
                        self.name,
                        f"schematic_no_connect references non-existent port '{element.schematic_port_id}'",
                        element_id=element.schematic_no_connect_id,
                    )

        return result

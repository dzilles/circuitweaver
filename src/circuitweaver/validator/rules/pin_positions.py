"""Validation rule for checking schematic_port positions match actual symbol pins."""

import logging
from typing import Any

from circuitweaver.library.pinout import get_symbol_pinout, PinInfo
from circuitweaver.types.circuit_json import (
    CircuitElement,
    SchematicComponent,
    SchematicPort,
    SourceComponent,
)
from circuitweaver.validator.result import ValidationResult
from circuitweaver.validator.rules.base import ValidationRule

logger = logging.getLogger(__name__)


class PinPositionsRule(ValidationRule):
    """Validate that schematic_port positions match actual KiCad symbol pin positions."""

    @property
    def name(self) -> str:
        return "pin_positions"

    @property
    def description(self) -> str:
        return (
            "Checks that schematic_port center coordinates match "
            "the actual pin positions from KiCad symbol definitions."
        )

    def validate(
        self,
        elements: list[CircuitElement],
        context: dict[str, Any],
    ) -> ValidationResult:
        result = ValidationResult()

        # Index elements
        source_components: dict[str, SourceComponent] = {}
        schematic_components: dict[str, SchematicComponent] = {}
        schematic_ports: dict[str, list[SchematicPort]] = {}  # keyed by schematic_component_id

        for elem in elements:
            if isinstance(elem, SourceComponent):
                source_components[elem.source_component_id] = elem
            elif isinstance(elem, SchematicComponent):
                schematic_components[elem.schematic_component_id] = elem
            elif isinstance(elem, SchematicPort):
                comp_id = elem.schematic_component_id
                if comp_id not in schematic_ports:
                    schematic_ports[comp_id] = []
                schematic_ports[comp_id].append(elem)

        # Validate each schematic component's ports
        for comp_id, comp in schematic_components.items():
            ports = schematic_ports.get(comp_id, [])
            if not ports:
                continue

            # Resolve symbol ID - prefer symbol_name if available
            symbol_id = None
            if comp.symbol_name and ":" in comp.symbol_name:
                symbol_id = comp.symbol_name
            elif ":" in comp.source_component_id:
                symbol_id = comp.source_component_id
            elif comp.source_component_id in source_components:
                source = source_components[comp.source_component_id]
                symbol_name = source.name.rstrip("0123456789")
                symbol_id = f"Device:{symbol_name}"

            if not symbol_id:
                continue  # Can't resolve, skip

            # Get actual pin positions from library
            try:
                pin_infos = get_symbol_pinout(symbol_id)
            except ValueError as e:
                logger.warning(f"Could not get pinout for {symbol_id}: {e}")
                continue

            # Build map of pin number/name to expected position
            actual_pins = self._compute_actual_positions(
                pin_infos, comp.center.x, comp.center.y, comp.rotation
            )

            # Check each port
            for port in ports:
                pin_id = port.source_port_id
                expected = actual_pins.get(pin_id)

                if expected is None:
                    # Try matching by name if number didn't match
                    for pin in pin_infos:
                        if pin.name == pin_id:
                            expected = actual_pins.get(pin.number)
                            break

                if expected is None:
                    result.add_error(
                        self.name,
                        f"Port '{port.schematic_port_id}' references unknown pin '{pin_id}' on symbol '{symbol_id}'",
                        element_id=port.schematic_port_id,
                    )
                    continue

                exp_x, exp_y = expected
                if port.center.x != exp_x or port.center.y != exp_y:
                    result.add_error(
                        self.name,
                        f"Port '{port.schematic_port_id}' position ({port.center.x}, {port.center.y}) "
                        f"doesn't match actual pin position ({exp_x}, {exp_y}) for pin '{pin_id}' "
                        f"on component '{comp_id}'",
                        element_id=port.schematic_port_id,
                    )

        return result

    def _compute_actual_positions(
        self,
        pins: list[PinInfo],
        center_x: int,
        center_y: int,
        rotation: int,
    ) -> dict[str, tuple[int, int]]:
        """Compute actual pin positions after component placement and rotation.

        Args:
            pins: Pin info from symbol definition.
            center_x: Component center X in grid units.
            center_y: Component center Y in grid units.
            rotation: Component rotation in degrees (0, 90, 180, 270).

        Returns:
            Dict mapping pin number to (x, y) grid position.
        """
        result: dict[str, tuple[int, int]] = {}

        for pin in pins:
            # Pin offset from component center
            # Note: Y negation is handled in get_symbol_pinout(), so just use offset directly
            px, py = pin.grid_offset.x, pin.grid_offset.y

            # Apply rotation (KiCad uses clockwise rotation)
            if rotation == 90:
                px, py = py, -px
            elif rotation == 180:
                px, py = -px, -py
            elif rotation == 270:
                px, py = -py, px

            # Add component center offset
            final_x = center_x + px
            final_y = center_y + py

            result[pin.number] = (final_x, final_y)

        return result

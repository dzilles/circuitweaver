"""Validation rule for ensuring all symbol pins are defined as source_ports."""

from collections import defaultdict
from typing import Any

from circuitweaver.library.pinout import get_symbol_pinout
from circuitweaver.types.circuit_json import (
    CircuitElement,
    SourceComponent,
    SourcePort,
)
from circuitweaver.validator.result import ValidationResult
from circuitweaver.validator.rules.base import ValidationRule


class SourcePortCompletenessRule(ValidationRule):
    """Validate that all pins of a KiCad symbol have corresponding source_ports.

    Checks:
    - Each source_component has a symbol_id (Warning if missing)
    - Each pin defined in the KiCad symbol has a matching source_port (Error if missing)
    """

    @property
    def name(self) -> str:
        return "source_port_completeness"

    @property
    def description(self) -> str:
        return "All pins of the KiCad symbol must be defined as source_ports"

    def validate(
        self,
        elements: list[CircuitElement],
        context: dict[str, Any],
    ) -> ValidationResult:
        result = ValidationResult()

        # Group defined ports by component ID
        component_ports: dict[str, list[SourcePort]] = defaultdict(list)
        for element in elements:
            if isinstance(element, SourcePort):
                component_ports[element.source_component_id].append(element)

        # Check each component
        for element in elements:
            if not isinstance(element, SourceComponent):
                continue

            comp_id = element.source_component_id
            
            # 1. Check if symbol_id is present
            if not element.symbol_id:
                result.add_warning(
                    self.name,
                    f"source_component '{comp_id}' (name: '{element.name}') is missing 'symbol_id'. "
                    f"Validation cannot check for missing pins.",
                    element_id=comp_id,
                )
                continue

            # 2. Fetch expected pins from KiCad library
            try:
                expected_pins = get_symbol_pinout(element.symbol_id)
            except ValueError as e:
                result.add_error(
                    self.name,
                    f"Could not fetch pinout for symbol '{element.symbol_id}' "
                    f"referenced by component '{comp_id}': {e}",
                    element_id=comp_id,
                )
                continue

            # 3. Check for completeness
            defined_ports = component_ports[comp_id]
            
            # Create sets for easy lookup of defined pin numbers and names
            # We treat both as strings for comparison
            defined_numbers = {str(p.pin_number) for p in defined_ports if p.pin_number is not None}
            defined_names = {p.name for p in defined_ports}

            for expected_pin in expected_pins:
                pin_num = str(expected_pin.number)
                pin_name = expected_pin.name
                
                # A pin is considered defined if either its number or its name matches
                if pin_num not in defined_numbers and pin_name not in defined_names:
                    result.add_error(
                        self.name,
                        f"source_component '{comp_id}' is missing port definition "
                        f"for symbol pin {pin_num} (name: '{pin_name}')",
                        element_id=comp_id,
                    )

        return result

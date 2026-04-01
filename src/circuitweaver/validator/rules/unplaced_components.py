"""Validation rule for detecting source_components without schematic placement."""

from typing import Any, Set

from circuitweaver.types.circuit_json import (
    CircuitElement,
    SchematicComponent,
    SourceComponent,
)
from circuitweaver.validator.result import ValidationResult
from circuitweaver.validator.rules.base import ValidationRule


class UnplacedComponentsRule(ValidationRule):
    """Warn when source_components don't have corresponding schematic_components.

    Every source_component should have at least one schematic_component that
    references it via source_component_id. If a part is defined in the BOM
    but not placed on the schematic, it won't appear in the output.
    """

    @property
    def name(self) -> str:
        return "unplaced_components"

    @property
    def description(self) -> str:
        return "Checks that all source_components have schematic placements"

    def validate(
        self,
        elements: list[CircuitElement],
        context: dict[str, Any],
    ) -> ValidationResult:
        result = ValidationResult()

        # Collect all source_component IDs
        source_component_ids: Set[str] = set()
        source_components: dict[str, SourceComponent] = {}

        # Collect all source_component_ids referenced by schematic_components
        placed_component_ids: Set[str] = set()

        for element in elements:
            if isinstance(element, SourceComponent):
                source_component_ids.add(element.source_component_id)
                source_components[element.source_component_id] = element
            elif isinstance(element, SchematicComponent):
                # Skip hierarchy blocks - they don't need source_components
                if not element.source_component_id.startswith("hierarchy:"):
                    placed_component_ids.add(element.source_component_id)

        # Find source_components without schematic placement
        unplaced = source_component_ids - placed_component_ids

        for comp_id in sorted(unplaced):
            comp = source_components.get(comp_id)
            if comp:
                result.add_warning(
                    self.name,
                    f"Source component '{comp_id}' ({comp.name}: {comp.value}) "
                    f"has no schematic_component placement. "
                    f"Add a schematic_component with source_component_id: \"{comp_id}\" "
                    f"to place this part on the schematic.",
                    element_id=comp_id,
                )

        return result

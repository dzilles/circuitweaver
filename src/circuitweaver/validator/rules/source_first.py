"""Validation rule for source-first ordering."""

from typing import Any

from circuitweaver.types.circuit_json import (
    CircuitElement,
    SchematicComponent,
    SourceComponent,
)
from circuitweaver.validator.result import ValidationResult
from circuitweaver.validator.rules.base import ValidationRule


class SourceFirstRule(ValidationRule):
    """Ensure source_component is defined before schematic_component.

    The "Source First" rule requires that every schematic_component must
    reference a source_component that was defined earlier in the element list.
    """

    @property
    def name(self) -> str:
        return "source_first"

    @property
    def description(self) -> str:
        return "source_component must be defined before schematic_component references it"

    def validate(
        self,
        elements: list[CircuitElement],
        context: dict[str, Any],
    ) -> ValidationResult:
        result = ValidationResult()

        # Track source_component IDs we've seen so far (in order)
        seen_sources: set[str] = set()

        for i, element in enumerate(elements):
            if isinstance(element, SourceComponent):
                seen_sources.add(element.source_component_id)

            elif isinstance(element, SchematicComponent):
                source_id = element.source_component_id

                # Check for hierarchy references (these don't need source_component)
                if source_id.startswith("hierarchy:"):
                    continue

                # Check for library references (Device:R, etc.)
                if ":" in source_id and not source_id.startswith("hierarchy:"):
                    # This is a library reference, not a source_component reference
                    # Warn but don't error - might be intentional for simple cases
                    result.add_warning(
                        self.name,
                        f"schematic_component references library symbol '{source_id}' directly. "
                        f"Consider creating a source_component for BOM generation.",
                        element_id=element.schematic_component_id,
                        location={"index": i, "source_component_id": source_id},
                    )
                    continue

                # Check if source_component was defined before this schematic_component
                if source_id not in seen_sources:
                    # Check if it exists at all
                    all_sources = context.get("source_components", {})
                    if source_id in all_sources:
                        result.add_error(
                            self.name,
                            f"schematic_component references source_component '{source_id}' "
                            f"which is defined AFTER it (at index {i}). "
                            f"Move source_component before schematic_component.",
                            element_id=element.schematic_component_id,
                            location={"index": i, "source_component_id": source_id},
                        )
                    else:
                        result.add_error(
                            self.name,
                            f"schematic_component references non-existent source_component "
                            f"'{source_id}'",
                            element_id=element.schematic_component_id,
                            location={"index": i, "source_component_id": source_id},
                        )

        return result

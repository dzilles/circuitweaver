"""Validation rule for unique IDs."""

from typing import Any

from circuitweaver.types.circuit_json import (
    CircuitElement,
    SchematicBox,
    SchematicComponent,
    SchematicLine,
    SchematicNetLabel,
    SchematicPort,
    SchematicSheet,
    SchematicText,
    SchematicTrace,
    SourceComponent,
    SourceNet,
    SourcePort,
    SourceTrace,
)
from circuitweaver.validator.result import ValidationResult
from circuitweaver.validator.rules.base import ValidationRule


class UniqueIdsRule(ValidationRule):
    """Ensure all element IDs are unique.

    Each element type has its own ID field, and all IDs must be unique
    within that namespace.
    """

    @property
    def name(self) -> str:
        return "unique_ids"

    @property
    def description(self) -> str:
        return "All element IDs must be unique"

    def validate(
        self,
        elements: list[CircuitElement],
        context: dict[str, Any],
    ) -> ValidationResult:
        result = ValidationResult()

        # Track seen IDs by namespace
        seen: dict[str, dict[str, int]] = {
            "source_component": {},
            "source_port": {},
            "source_net": {},
            "source_trace": {},
            "schematic_sheet": {},
            "schematic_component": {},
            "schematic_port": {},
            "schematic_trace": {},
            "schematic_box": {},
            "schematic_text": {},
            "schematic_line": {},
        }

        for i, element in enumerate(elements):
            element_id, namespace = self._get_id_and_namespace(element)

            if element_id is None:
                continue

            if namespace not in seen:
                seen[namespace] = {}

            if element_id in seen[namespace]:
                first_index = seen[namespace][element_id]
                result.add_error(
                    self.name,
                    f"Duplicate {namespace} ID: '{element_id}' "
                    f"(first at index {first_index}, duplicate at index {i})",
                    element_id=element_id,
                    location={"first_index": first_index, "duplicate_index": i},
                )
            else:
                seen[namespace][element_id] = i

        return result

    def _get_id_and_namespace(
        self, element: CircuitElement
    ) -> tuple[str | None, str]:
        """Extract ID and namespace from an element."""
        if isinstance(element, SourceComponent):
            return element.source_component_id, "source_component"
        elif isinstance(element, SourcePort):
            return element.source_port_id, "source_port"
        elif isinstance(element, SourceNet):
            return element.source_net_id, "source_net"
        elif isinstance(element, SourceTrace):
            return element.source_trace_id, "source_trace"
        elif isinstance(element, SchematicSheet):
            return element.schematic_sheet_id, "schematic_sheet"
        elif isinstance(element, SchematicComponent):
            return element.schematic_component_id, "schematic_component"
        elif isinstance(element, SchematicPort):
            return element.schematic_port_id, "schematic_port"
        elif isinstance(element, SchematicTrace):
            return element.schematic_trace_id, "schematic_trace"
        elif isinstance(element, SchematicBox):
            return element.schematic_box_id, "schematic_box"
        elif isinstance(element, SchematicText):
            return element.schematic_text_id, "schematic_text"
        elif isinstance(element, SchematicLine):
            return element.schematic_line_id, "schematic_line"
        elif isinstance(element, SchematicNetLabel):
            # Net labels use source_net_id which can be repeated
            return None, "schematic_net_label"
        else:
            return None, "unknown"

"""Validation rule for hierarchical links."""

from typing import Any

from circuitweaver.types.circuit_json import (
    CircuitElement,
    SchematicComponent,
    SchematicNetLabel,
    SchematicSheet,
)
from circuitweaver.validator.result import ValidationResult
from circuitweaver.validator.rules.base import ValidationRule


class HierarchyLinksRule(ValidationRule):
    """Ensure hierarchical links are consistent.

    This rule checks that:
    - Sheet blocks (hierarchy:*) reference existing subcircuit_ids
    - Hierarchical port labels match between root and sub-sheets
    - All referenced subcircuits have corresponding sheets
    """

    @property
    def name(self) -> str:
        return "hierarchy_links"

    @property
    def description(self) -> str:
        return "Hierarchical links must be consistent between sheets"

    def validate(
        self,
        elements: list[CircuitElement],
        context: dict[str, Any],
    ) -> ValidationResult:
        result = ValidationResult()

        # Collect sheets by subcircuit_id
        sheets_by_subcircuit: dict[str, SchematicSheet] = {}
        for element in elements:
            if isinstance(element, SchematicSheet) and element.subcircuit_id:
                sheets_by_subcircuit[element.subcircuit_id] = element

        # Collect hierarchy references from components
        hierarchy_refs: list[tuple[SchematicComponent, str]] = []
        for element in elements:
            if isinstance(element, SchematicComponent):
                source_id = element.source_component_id
                if source_id.startswith("hierarchy:"):
                    subcircuit = source_id.split(":", 1)[1]
                    hierarchy_refs.append((element, subcircuit))

        # Collect net labels for matching
        net_labels_by_text: dict[str, list[SchematicNetLabel]] = {}
        for element in elements:
            if isinstance(element, SchematicNetLabel):
                if element.text not in net_labels_by_text:
                    net_labels_by_text[element.text] = []
                net_labels_by_text[element.text].append(element)

        # Check hierarchy references
        for component, subcircuit in hierarchy_refs:
            if subcircuit not in sheets_by_subcircuit:
                result.add_error(
                    self.name,
                    f"Sheet block references non-existent subcircuit '{subcircuit}'",
                    element_id=component.schematic_component_id,
                    location={
                        "source_component_id": component.source_component_id,
                        "expected_subcircuit_id": subcircuit,
                    },
                )
                continue

            # Check port labels if defined
            if component.port_labels:
                for port_name, label_text in component.port_labels.items():
                    if label_text not in net_labels_by_text:
                        result.add_warning(
                            self.name,
                            f"Hierarchical port '{port_name}' has label '{label_text}' "
                            f"but no matching SchematicNetLabel found in sub-sheet",
                            element_id=component.schematic_component_id,
                            location={
                                "port_name": port_name,
                                "label_text": label_text,
                                "subcircuit": subcircuit,
                            },
                        )

        # Check for orphaned sheets (sheets with subcircuit_id but no hierarchy reference)
        referenced_subcircuits = {sub for _, sub in hierarchy_refs}
        for subcircuit_id, sheet in sheets_by_subcircuit.items():
            if subcircuit_id == "root":
                continue  # Root sheet doesn't need a reference
            if subcircuit_id not in referenced_subcircuits:
                result.add_warning(
                    self.name,
                    f"Sheet '{sheet.name or sheet.schematic_sheet_id}' with "
                    f"subcircuit_id '{subcircuit_id}' has no hierarchy reference",
                    element_id=sheet.schematic_sheet_id,
                    location={"subcircuit_id": subcircuit_id},
                )

        return result

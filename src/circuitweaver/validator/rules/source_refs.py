"""Validation rule for source element references."""

from typing import Any

from circuitweaver.types.circuit_json import (
    CircuitElement,
    SourceComponent,
    SourceGroup,
    SourceNet,
    SourcePort,
    SourceTrace,
)
from circuitweaver.validator.result import ValidationResult
from circuitweaver.validator.rules.base import ValidationRule


class SourceReferencesRule(ValidationRule):
    """Validate that all source element references are valid.

    Checks:
    - source_port.source_component_id → valid source_component
    - source_trace.connected_source_port_ids → valid source_ports
    - source_trace.connected_source_net_ids → valid source_nets
    - *.subcircuit_id → valid source_group.subcircuit_id (if using groups)
    """

    @property
    def name(self) -> str:
        return "source_references"

    @property
    def description(self) -> str:
        return "All source element references must be valid"

    def validate(
        self,
        elements: list[CircuitElement],
        context: dict[str, Any],
    ) -> ValidationResult:
        result = ValidationResult()

        source_components = context["source_components"]
        source_ports = context["source_ports"]
        source_nets = context["source_nets"]
        source_groups = context["source_groups"]

        # Build set of valid subcircuit_ids from groups
        valid_subcircuit_ids: set[str] = set()
        for group in source_groups.values():
            if group.subcircuit_id:
                valid_subcircuit_ids.add(group.subcircuit_id)

        for element in elements:
            # Check source_port → source_component reference
            if isinstance(element, SourcePort):
                if element.source_component_id not in source_components:
                    result.add_error(
                        self.name,
                        f"source_port '{element.source_port_id}' references "
                        f"non-existent source_component '{element.source_component_id}'",
                        element_id=element.source_port_id,
                    )

            # Check source_trace → source_port references
            elif isinstance(element, SourceTrace):
                for port_id in element.connected_source_port_ids:
                    if port_id not in source_ports:
                        result.add_error(
                            self.name,
                            f"source_trace '{element.source_trace_id}' references "
                            f"non-existent source_port '{port_id}'",
                            element_id=element.source_trace_id,
                        )

                # Check source_trace → source_net references
                for net_id in element.connected_source_net_ids:
                    if net_id not in source_nets:
                        result.add_error(
                            self.name,
                            f"source_trace '{element.source_trace_id}' references "
                            f"non-existent source_net '{net_id}'",
                            element_id=element.source_trace_id,
                        )

            # Check subcircuit_id references (if using groups)
            if valid_subcircuit_ids:
                subcircuit_id = None
                element_id = None

                if isinstance(element, SourceComponent):
                    subcircuit_id = element.subcircuit_id
                    element_id = element.source_component_id
                elif isinstance(element, SourcePort):
                    subcircuit_id = element.subcircuit_id
                    element_id = element.source_port_id
                elif isinstance(element, SourceNet):
                    subcircuit_id = element.subcircuit_id
                    element_id = element.source_net_id
                elif isinstance(element, SourceTrace):
                    subcircuit_id = element.subcircuit_id
                    element_id = element.source_trace_id

                if subcircuit_id and subcircuit_id not in valid_subcircuit_ids:
                    result.add_warning(
                        self.name,
                        f"Element '{element_id}' references subcircuit_id "
                        f"'{subcircuit_id}' which is not defined by any source_group",
                        element_id=element_id,
                    )

            # Check source_group hierarchy references
            if isinstance(element, SourceGroup):
                if element.parent_source_group_id:
                    if element.parent_source_group_id not in source_groups:
                        result.add_error(
                            self.name,
                            f"source_group '{element.source_group_id}' references "
                            f"non-existent parent_source_group_id "
                            f"'{element.parent_source_group_id}'",
                            element_id=element.source_group_id,
                        )

        return result

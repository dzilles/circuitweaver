"""Validation rule for trace connections."""

from collections import defaultdict
from typing import Any

from circuitweaver.types.circuit_json import (
    CircuitElement,
    SourceTrace,
)
from circuitweaver.validator.result import ValidationResult
from circuitweaver.validator.rules.base import ValidationRule


class TraceConnectionsRule(ValidationRule):
    """Validate that source_trace connections are logically valid.

    Checks:
    - Each trace connects at least one port (can also include nets)
    - No duplicate port references in the same trace
    - Warns about ports connected to multiple traces (might be intentional)
    """

    @property
    def name(self) -> str:
        return "trace_connections"

    @property
    def description(self) -> str:
        return "Trace connections must be logically valid"

    def validate(
        self,
        elements: list[CircuitElement],
        context: dict[str, Any],
    ) -> ValidationResult:
        result = ValidationResult()

        # Track which traces each port appears in
        port_to_traces: dict[str, list[str]] = defaultdict(list)

        for element in elements:
            if not isinstance(element, SourceTrace):
                continue

            trace_id = element.source_trace_id
            port_ids = element.connected_source_port_ids
            net_ids = element.connected_source_net_ids

            # Check: at least one port
            if not port_ids:
                result.add_error(
                    self.name,
                    f"source_trace '{trace_id}' has no connected ports. "
                    f"A trace must connect at least one port.",
                    element_id=trace_id,
                )
                continue

            # Check: no duplicate ports in same trace
            seen_ports: set[str] = set()
            for port_id in port_ids:
                if port_id in seen_ports:
                    result.add_error(
                        self.name,
                        f"source_trace '{trace_id}' references port "
                        f"'{port_id}' multiple times",
                        element_id=trace_id,
                    )
                else:
                    seen_ports.add(port_id)
                    port_to_traces[port_id].append(trace_id)

            # Check: no duplicate nets in same trace
            seen_nets: set[str] = set()
            for net_id in net_ids:
                if net_id in seen_nets:
                    result.add_warning(
                        self.name,
                        f"source_trace '{trace_id}' references net "
                        f"'{net_id}' multiple times",
                        element_id=trace_id,
                    )
                else:
                    seen_nets.add(net_id)

            # Check: meaningful connection
            # A trace with only 1 port and no nets is just a stub
            if len(port_ids) == 1 and not net_ids:
                result.add_warning(
                    self.name,
                    f"source_trace '{trace_id}' connects only one port "
                    f"'{port_ids[0]}' and no nets. This creates a floating connection.",
                    element_id=trace_id,
                )

        # Warn about ports in multiple traces (might indicate error)
        for port_id, trace_ids in port_to_traces.items():
            if len(trace_ids) > 1:
                # This might be intentional (e.g., bus connections)
                # but worth a warning
                result.add_warning(
                    self.name,
                    f"Port '{port_id}' appears in multiple traces: "
                    f"{', '.join(trace_ids)}. This may be intentional for "
                    f"bus connections, but verify it's correct.",
                    element_id=port_id,
                )

        return result

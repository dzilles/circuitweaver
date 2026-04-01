"""Validation rule for orthogonal traces."""

from typing import Any

from circuitweaver.types.circuit_json import CircuitElement, SchematicTrace
from circuitweaver.validator.result import ValidationResult
from circuitweaver.validator.rules.base import ValidationRule


class OrthogonalTracesRule(ValidationRule):
    """Ensure all trace edges are strictly orthogonal.

    Every trace edge must be either:
    - Horizontal: from.y == to.y (X changes, Y constant)
    - Vertical: from.x == to.x (Y changes, X constant)

    Diagonal edges (both X and Y changing) are not allowed.
    """

    @property
    def name(self) -> str:
        return "orthogonal_traces"

    @property
    def description(self) -> str:
        return "All trace edges must be horizontal or vertical (no diagonals)"

    def validate(
        self,
        elements: list[CircuitElement],
        context: dict[str, Any],
    ) -> ValidationResult:
        result = ValidationResult()

        for element in elements:
            if not isinstance(element, SchematicTrace):
                continue

            trace_id = element.schematic_trace_id

            for i, edge in enumerate(element.edges):
                from_x, from_y = edge.from_.x, edge.from_.y
                to_x, to_y = edge.to.x, edge.to.y

                is_horizontal = from_y == to_y
                is_vertical = from_x == to_x

                if not is_horizontal and not is_vertical:
                    # Diagonal edge detected
                    result.add_error(
                        self.name,
                        f"Edge {i} is diagonal: ({from_x},{from_y}) -> ({to_x},{to_y}). "
                        f"Split into horizontal and vertical segments.",
                        element_id=trace_id,
                        location={
                            "edge_index": i,
                            "from": {"x": from_x, "y": from_y},
                            "to": {"x": to_x, "y": to_y},
                        },
                    )

                elif is_horizontal and is_vertical:
                    # Zero-length edge (from == to)
                    result.add_warning(
                        self.name,
                        f"Edge {i} has zero length: ({from_x},{from_y}) -> ({to_x},{to_y})",
                        element_id=trace_id,
                        location={
                            "edge_index": i,
                            "from": {"x": from_x, "y": from_y},
                            "to": {"x": to_x, "y": to_y},
                        },
                    )

            # Check edge continuity
            self._check_continuity(result, element)

        return result

    def _check_continuity(
        self,
        result: ValidationResult,
        trace: SchematicTrace,
    ) -> None:
        """Check that edges connect end-to-end."""
        edges = trace.edges

        for i in range(len(edges) - 1):
            current_end = edges[i].to
            next_start = edges[i + 1].from_

            if current_end.x != next_start.x or current_end.y != next_start.y:
                result.add_error(
                    self.name,
                    f"Edge {i} end ({current_end.x},{current_end.y}) does not connect "
                    f"to edge {i+1} start ({next_start.x},{next_start.y})",
                    element_id=trace.schematic_trace_id,
                    location={
                        "edge_index": i,
                        "gap_from": {"x": current_end.x, "y": current_end.y},
                        "gap_to": {"x": next_start.x, "y": next_start.y},
                    },
                )

"""Validation rule for integer coordinates."""

from typing import Any

from circuitweaver.types.circuit_json import (
    CircuitElement,
    SchematicBox,
    SchematicComponent,
    SchematicNetLabel,
    SchematicPort,
    SchematicText,
    SchematicTrace,
)
from circuitweaver.validator.result import ValidationResult
from circuitweaver.validator.rules.base import ValidationRule


class IntegerCoordsRule(ValidationRule):
    """Ensure all coordinates are integers (grid units).

    Circuit JSON uses an integer grid system where 1 unit = 2.54mm.
    Floating point coordinates are not allowed.
    """

    @property
    def name(self) -> str:
        return "integer_coords"

    @property
    def description(self) -> str:
        return "All coordinates must be integers (grid units)"

    def validate(
        self,
        elements: list[CircuitElement],
        context: dict[str, Any],
    ) -> ValidationResult:
        result = ValidationResult()

        for element in elements:
            if isinstance(element, SchematicComponent):
                self._check_point(
                    result,
                    element.center.x,
                    element.center.y,
                    element.schematic_component_id,
                    "center",
                )
                if element.size:
                    self._check_size(
                        result,
                        element.size.width,
                        element.size.height,
                        element.schematic_component_id,
                    )

            elif isinstance(element, SchematicPort):
                self._check_point(
                    result,
                    element.center.x,
                    element.center.y,
                    element.schematic_port_id,
                    "center",
                )

            elif isinstance(element, SchematicTrace):
                for i, edge in enumerate(element.edges):
                    self._check_point(
                        result,
                        edge.from_.x,
                        edge.from_.y,
                        element.schematic_trace_id,
                        f"edge[{i}].from",
                    )
                    self._check_point(
                        result,
                        edge.to.x,
                        edge.to.y,
                        element.schematic_trace_id,
                        f"edge[{i}].to",
                    )

            elif isinstance(element, SchematicBox):
                self._check_point(
                    result,
                    element.x,
                    element.y,
                    element.schematic_box_id,
                    "position",
                )
                self._check_size(
                    result,
                    element.width,
                    element.height,
                    element.schematic_box_id,
                )

            elif isinstance(element, SchematicNetLabel):
                self._check_point(
                    result,
                    element.center.x,
                    element.center.y,
                    element.source_net_id,
                    "center",
                )

            elif isinstance(element, SchematicText):
                self._check_point(
                    result,
                    element.position.x,
                    element.position.y,
                    element.schematic_text_id,
                    "position",
                )

        return result

    def _check_point(
        self,
        result: ValidationResult,
        x: Any,
        y: Any,
        element_id: str,
        field: str,
    ) -> None:
        """Check that x and y are integers."""
        if not isinstance(x, int) or isinstance(x, bool):
            result.add_error(
                self.name,
                f"{field}.x must be an integer, got {type(x).__name__}: {x}",
                element_id=element_id,
                location={"field": f"{field}.x", "value": x},
            )
        if not isinstance(y, int) or isinstance(y, bool):
            result.add_error(
                self.name,
                f"{field}.y must be an integer, got {type(y).__name__}: {y}",
                element_id=element_id,
                location={"field": f"{field}.y", "value": y},
            )

    def _check_size(
        self,
        result: ValidationResult,
        width: Any,
        height: Any,
        element_id: str,
    ) -> None:
        """Check that width and height are integers."""
        if not isinstance(width, int) or isinstance(width, bool):
            result.add_error(
                self.name,
                f"width must be an integer, got {type(width).__name__}: {width}",
                element_id=element_id,
                location={"field": "width", "value": width},
            )
        if not isinstance(height, int) or isinstance(height, bool):
            result.add_error(
                self.name,
                f"height must be an integer, got {type(height).__name__}: {height}",
                element_id=element_id,
                location={"field": "height", "value": height},
            )

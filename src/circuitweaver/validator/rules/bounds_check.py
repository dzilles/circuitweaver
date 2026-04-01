"""Validation rule for component bounds checking."""

from typing import Any

from circuitweaver.types.circuit_json import (
    CircuitElement,
    SchematicBox,
    SchematicComponent,
    SchematicText,
    SchematicTrace,
)
from circuitweaver.validator.result import ValidationResult
from circuitweaver.validator.rules.base import ValidationRule


class BoundsCheckRule(ValidationRule):
    """Ensure components and traces stay within their parent box bounds.

    This rule checks that:
    - Components inside a box don't extend outside box boundaries
    - Traces inside a box don't have edges outside box boundaries
    - Text inside a box is positioned within bounds
    """

    @property
    def name(self) -> str:
        return "bounds_check"

    @property
    def description(self) -> str:
        return "Components and traces must stay within their parent box bounds"

    def validate(
        self,
        elements: list[CircuitElement],
        context: dict[str, Any],
    ) -> ValidationResult:
        result = ValidationResult()

        boxes = context.get("schematic_boxes", {})

        # If no boxes, nothing to check
        if not boxes:
            return result

        # Build a simple spatial index of boxes
        box_list = list(boxes.values())

        for element in elements:
            if isinstance(element, SchematicComponent):
                self._check_component_bounds(result, element, box_list)
            elif isinstance(element, SchematicTrace):
                self._check_trace_bounds(result, element, box_list)
            elif isinstance(element, SchematicText):
                if element.schematic_box_id:
                    self._check_text_bounds(result, element, boxes)

        return result

    def _check_component_bounds(
        self,
        result: ValidationResult,
        component: SchematicComponent,
        boxes: list[SchematicBox],
    ) -> None:
        """Check if a component is within any containing box."""
        cx, cy = component.center.x, component.center.y

        # Find boxes that might contain this component
        containing_boxes = [
            box for box in boxes if self._point_in_box(cx, cy, box)
        ]

        # If component has a size, check all corners
        if component.size:
            hw = component.size.width // 2
            hh = component.size.height // 2
            corners = [
                (cx - hw, cy - hh),
                (cx + hw, cy - hh),
                (cx - hw, cy + hh),
                (cx + hw, cy + hh),
            ]

            for box in containing_boxes:
                for corner_x, corner_y in corners:
                    if not self._point_in_box(corner_x, corner_y, box):
                        result.add_warning(
                            self.name,
                            f"Component extends outside box '{box.schematic_box_id}' "
                            f"at corner ({corner_x}, {corner_y})",
                            element_id=component.schematic_component_id,
                            location={
                                "center": {"x": cx, "y": cy},
                                "box_id": box.schematic_box_id,
                            },
                        )
                        break

    def _check_trace_bounds(
        self,
        result: ValidationResult,
        trace: SchematicTrace,
        boxes: list[SchematicBox],
    ) -> None:
        """Check if trace edges stay within boxes."""
        # Collect all points in the trace
        points: list[tuple[int, int]] = []
        for edge in trace.edges:
            points.append((edge.from_.x, edge.from_.y))
            points.append((edge.to.x, edge.to.y))

        # Find boxes that contain the first point
        if not points:
            return

        first_x, first_y = points[0]
        containing_boxes = [
            box for box in boxes if self._point_in_box(first_x, first_y, box)
        ]

        # Check all points against containing boxes
        for box in containing_boxes:
            for px, py in points:
                if not self._point_in_box(px, py, box):
                    result.add_warning(
                        self.name,
                        f"Trace has point ({px}, {py}) outside its containing box "
                        f"'{box.schematic_box_id}'",
                        element_id=trace.schematic_trace_id,
                        location={
                            "point": {"x": px, "y": py},
                            "box_id": box.schematic_box_id,
                        },
                    )
                    break

    def _check_text_bounds(
        self,
        result: ValidationResult,
        text: SchematicText,
        boxes: dict[str, SchematicBox],
    ) -> None:
        """Check if text is within its parent box."""
        box_id = text.schematic_box_id
        if box_id not in boxes:
            result.add_error(
                self.name,
                f"Text references non-existent box '{box_id}'",
                element_id=text.schematic_text_id,
                location={"box_id": box_id},
            )
            return

        box = boxes[box_id]
        tx, ty = text.position.x, text.position.y

        if not self._point_in_box(tx, ty, box):
            result.add_warning(
                self.name,
                f"Text position ({tx}, {ty}) is outside its parent box "
                f"'{box_id}'",
                element_id=text.schematic_text_id,
                location={
                    "position": {"x": tx, "y": ty},
                    "box_id": box_id,
                },
            )

    def _point_in_box(self, x: int, y: int, box: SchematicBox) -> bool:
        """Check if a point is inside a box (inclusive)."""
        return (
            box.x <= x <= box.x + box.width
            and box.y <= y <= box.y + box.height
        )

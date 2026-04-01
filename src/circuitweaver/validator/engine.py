"""Main validation engine for Circuit JSON files."""

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from circuitweaver.types.circuit_json import (
    CircuitElement,
    SchematicBox,
    SchematicComponent,
    SchematicTrace,
    SourceComponent,
)
from circuitweaver.validator.result import ValidationResult
from circuitweaver.validator.rules import (
    BoundsCheckRule,
    HierarchyLinksRule,
    IntegerCoordsRule,
    OrthogonalTracesRule,
    PinPositionsRule,
    SourceFirstRule,
    UnconnectedPinsRule,
    UniqueIdsRule,
    UnplacedComponentsRule,
    ValidationRule,
)

logger = logging.getLogger(__name__)


# All validation rules in order of execution
VALIDATION_RULES: list[type[ValidationRule]] = [
    IntegerCoordsRule,
    OrthogonalTracesRule,
    UniqueIdsRule,
    SourceFirstRule,
    BoundsCheckRule,
    HierarchyLinksRule,
    PinPositionsRule,
    UnconnectedPinsRule,
    UnplacedComponentsRule,
]


def validate_circuit_file(file_path: Path) -> ValidationResult:
    """Validate a Circuit JSON file.

    Args:
        file_path: Path to the Circuit JSON file.

    Returns:
        ValidationResult with errors and warnings.
    """
    result = ValidationResult()

    # Load and parse JSON
    try:
        with open(file_path) as f:
            raw_data = json.load(f)
    except json.JSONDecodeError as e:
        result.add_error("json_parse", f"Invalid JSON: {e}")
        return result
    except FileNotFoundError:
        result.add_error("file_not_found", f"File not found: {file_path}")
        return result

    # Validate it's a list
    if not isinstance(raw_data, list):
        result.add_error(
            "structure",
            f"Circuit JSON must be a list of elements, got {type(raw_data).__name__}",
        )
        return result

    # Parse elements with Pydantic
    elements: list[CircuitElement] = []
    for i, raw_element in enumerate(raw_data):
        if not isinstance(raw_element, dict):
            result.add_error(
                "structure",
                f"Element {i} must be an object, got {type(raw_element).__name__}",
            )
            continue

        if "type" not in raw_element:
            result.add_error("structure", f"Element {i} missing 'type' field")
            continue

        try:
            element = _parse_element(raw_element)
            elements.append(element)
        except PydanticValidationError as e:
            for error in e.errors():
                loc = ".".join(str(x) for x in error["loc"])
                result.add_error(
                    "schema",
                    f"Element {i}: {loc} - {error['msg']}",
                    element_id=raw_element.get("source_component_id")
                    or raw_element.get("schematic_component_id")
                    or raw_element.get("schematic_trace_id"),
                )
        except ValueError as e:
            result.add_error("schema", f"Element {i}: {e}")

    # If we have schema errors, don't run rule validation
    if not result.is_valid:
        return result

    # Build context for rules
    context = _build_validation_context(elements)

    # Run all validation rules
    for rule_class in VALIDATION_RULES:
        rule = rule_class()
        rule_result = rule.validate(elements, context)
        result.merge(rule_result)

    return result


def _parse_element(raw: dict[str, Any]) -> CircuitElement:
    """Parse a raw dict into a CircuitElement."""
    element_type = raw.get("type")

    # Import all element types
    from circuitweaver.types.circuit_json import (
        SchematicBox,
        SchematicComponent,
        SchematicError,
        SchematicLine,
        SchematicNetLabel,
        SchematicNoConnect,
        SchematicPort,
        SchematicSheet,
        SchematicText,
        SchematicTrace,
        SourceComponent,
        SourceNet,
        SourcePort,
        SourceTrace,
    )

    type_map = {
        "source_component": SourceComponent,
        "source_port": SourcePort,
        "source_net": SourceNet,
        "source_trace": SourceTrace,
        "schematic_sheet": SchematicSheet,
        "schematic_component": SchematicComponent,
        "schematic_port": SchematicPort,
        "schematic_trace": SchematicTrace,
        "schematic_box": SchematicBox,
        "schematic_net_label": SchematicNetLabel,
        "schematic_text": SchematicText,
        "schematic_line": SchematicLine,
        "schematic_error": SchematicError,
        "schematic_no_connect": SchematicNoConnect,
    }

    if element_type not in type_map:
        valid_types = ", ".join(sorted(type_map.keys()))
        raise ValueError(
            f"Unknown element type: '{element_type}'. "
            f"Valid types are: {valid_types}."
        )

    return type_map[element_type].model_validate(raw)


def _build_validation_context(elements: list[CircuitElement]) -> dict[str, Any]:
    """Build a context dictionary for validation rules."""
    source_components: dict[str, SourceComponent] = {}
    schematic_components: dict[str, SchematicComponent] = {}
    schematic_boxes: dict[str, SchematicBox] = {}
    traces: list[SchematicTrace] = []
    all_ids: set[str] = set()

    for element in elements:
        if isinstance(element, SourceComponent):
            source_components[element.source_component_id] = element
            all_ids.add(element.source_component_id)
        elif isinstance(element, SchematicComponent):
            schematic_components[element.schematic_component_id] = element
            all_ids.add(element.schematic_component_id)
        elif isinstance(element, SchematicBox):
            schematic_boxes[element.schematic_box_id] = element
            all_ids.add(element.schematic_box_id)
        elif isinstance(element, SchematicTrace):
            traces.append(element)
            all_ids.add(element.schematic_trace_id)

    return {
        "source_components": source_components,
        "schematic_components": schematic_components,
        "schematic_boxes": schematic_boxes,
        "traces": traces,
        "all_ids": all_ids,
        "elements": elements,
    }

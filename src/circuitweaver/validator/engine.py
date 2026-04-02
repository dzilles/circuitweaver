"""Main validation engine for Circuit JSON files."""

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from circuitweaver.types.circuit_json import (
    CircuitElement,
    SourceComponent,
    SourceGroup,
    SourceNet,
    SourcePort,
    SourceTrace,
)
from circuitweaver.validator.result import ValidationResult
from circuitweaver.validator.rules import (
    SourcePortCompletenessRule,
    SourceReferencesRule,
    TraceConnectionsRule,
    UniqueIdsRule,
    ValidationRule,
)

logger = logging.getLogger(__name__)


# All validation rules in order of execution
VALIDATION_RULES: list[type[ValidationRule]] = [
    UniqueIdsRule,
    SourceReferencesRule,
    TraceConnectionsRule,
    SourcePortCompletenessRule,
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
                    element_id=_get_element_id_from_raw(raw_element),
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

    type_map = {
        "source_component": SourceComponent,
        "source_port": SourcePort,
        "source_net": SourceNet,
        "source_trace": SourceTrace,
        "source_group": SourceGroup,
    }

    if element_type not in type_map:
        valid_types = ", ".join(sorted(type_map.keys()))
        raise ValueError(
            f"Unknown element type: '{element_type}'. "
            f"Valid types are: {valid_types}."
        )

    return type_map[element_type].model_validate(raw)


def _get_element_id_from_raw(raw: dict[str, Any]) -> str | None:
    """Extract element ID from raw dict."""
    for key in [
        "source_component_id",
        "source_port_id",
        "source_net_id",
        "source_trace_id",
        "source_group_id",
    ]:
        if key in raw:
            return raw[key]
    return None


def _build_validation_context(elements: list[CircuitElement]) -> dict[str, Any]:
    """Build a context dictionary for validation rules."""
    source_components: dict[str, SourceComponent] = {}
    source_ports: dict[str, SourcePort] = {}
    source_nets: dict[str, SourceNet] = {}
    source_traces: dict[str, SourceTrace] = {}
    source_groups: dict[str, SourceGroup] = {}

    # Also index by subcircuit_id
    subcircuit_ids: set[str] = set()

    for element in elements:
        if isinstance(element, SourceComponent):
            source_components[element.source_component_id] = element
            if element.subcircuit_id:
                subcircuit_ids.add(element.subcircuit_id)
        elif isinstance(element, SourcePort):
            source_ports[element.source_port_id] = element
        elif isinstance(element, SourceNet):
            source_nets[element.source_net_id] = element
        elif isinstance(element, SourceTrace):
            source_traces[element.source_trace_id] = element
        elif isinstance(element, SourceGroup):
            source_groups[element.source_group_id] = element
            if element.subcircuit_id:
                subcircuit_ids.add(element.subcircuit_id)

    return {
        "source_components": source_components,
        "source_ports": source_ports,
        "source_nets": source_nets,
        "source_traces": source_traces,
        "source_groups": source_groups,
        "subcircuit_ids": subcircuit_ids,
        "elements": elements,
    }

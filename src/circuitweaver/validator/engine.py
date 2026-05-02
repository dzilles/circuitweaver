"""Main validation engine for Circuit JSON files."""

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from circuitweaver.io import (
    describe_unknown_field,
    get_element_id_from_raw,
    get_unknown_fields,
    parse_element,
)
from circuitweaver.types import (
    CircuitElement,
    SchematicComponent,
    SchematicNetLabel,
    SchematicNoConnect,
    SchematicPort,
    SchematicTrace,
    SourceComponent,
    SourceGroup,
    SourceNet,
    SourcePort,
    SourceTrace,
)
from circuitweaver.validator.result import ValidationResult
from circuitweaver.validator.rules import (
    DanglingLabelsRule,
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
    DanglingLabelsRule,
]

VALIDATION_PROFILES: dict[str, list[type[ValidationRule]]] = {
    "source": [
        UniqueIdsRule,
        SourceReferencesRule,
        TraceConnectionsRule,
        SourcePortCompletenessRule,
    ],
    "schematic": [UniqueIdsRule, SourceReferencesRule, DanglingLabelsRule],
    "compile-ready": [
        UniqueIdsRule,
        SourceReferencesRule,
        TraceConnectionsRule,
        SourcePortCompletenessRule,
        DanglingLabelsRule,
    ],
    "erc-ready": [
        UniqueIdsRule,
        SourceReferencesRule,
        TraceConnectionsRule,
        SourcePortCompletenessRule,
        DanglingLabelsRule,
    ],
}


def validate_circuit_file(file_path: Path, profile: str = "source") -> ValidationResult:
    """Validate a Circuit JSON file.

    Args:
        file_path: Path to the Circuit JSON file.

    Returns:
        ValidationResult with errors and warnings.
    """
    if profile not in VALIDATION_PROFILES:
        raise ValueError(
            f"Unknown validation profile: {profile}. "
            f"Available profiles: {', '.join(sorted(VALIDATION_PROFILES))}"
        )

    result = ValidationResult()

    # Load and parse JSON
    try:
        with open(file_path) as f:
            raw_data = json.load(f)
    except json.JSONDecodeError as e:
        result.add_error("json_parse", f"Invalid JSON: {e}", profile=profile)
        return result
    except FileNotFoundError:
        result.add_error("file_not_found", f"File not found: {file_path}", profile=profile)
        return result

    # Validate it's a list
    if not isinstance(raw_data, list):
        result.add_error(
            "structure",
            f"Circuit JSON must be a list of elements, got {type(raw_data).__name__}",
            profile=profile,
        )
        return result

    # Parse elements with Pydantic
    elements: list[CircuitElement] = []
    for i, raw_element in enumerate(raw_data):
        if not isinstance(raw_element, dict):
            result.add_error(
                "structure",
                f"Element {i} must be an object, got {type(raw_element).__name__}",
                profile=profile,
            )
            continue

        if "type" not in raw_element:
            result.add_error("structure", f"Element {i} missing 'type' field", profile=profile)
            continue

        for field_name in get_unknown_fields(raw_element):
            result.add_warning(
                "unknown_field",
                describe_unknown_field(raw_element, field_name),
                element_id=get_element_id_from_raw(raw_element),
                location={"element_index": i, "field": field_name},
                profile=profile,
            )

        try:
            element = parse_element(raw_element)
            elements.append(element)
        except PydanticValidationError as e:
            for error in e.errors():
                loc = ".".join(str(x) for x in error["loc"])
                result.add_error(
                    "schema",
                    f"Element {i}: {loc} - {error['msg']}",
                    element_id=get_element_id_from_raw(raw_element),
                    profile=profile,
                )
        except ValueError as e:
            result.add_error("schema", f"Element {i}: {e}", profile=profile)

    # If we have schema errors, don't run rule validation
    if not result.is_valid:
        return result

    # Build context for rules
    context = _build_validation_context(elements)

    for rule_class in VALIDATION_PROFILES[profile]:
        rule = rule_class()
        rule_result = rule.validate(elements, context)
        _tag_profile(rule_result, profile)
        result.merge(rule_result)

    _run_profile_checks(profile, elements, context, result)
    return result


def _tag_profile(result: ValidationResult, profile: str) -> None:
    for message in [*result.errors, *result.warnings]:
        message.profile = profile


def _run_profile_checks(
    profile: str,
    elements: list[CircuitElement],
    context: dict[str, Any],
    result: ValidationResult,
) -> None:
    if profile == "schematic":
        _validate_schematic_profile(elements, context, result, profile)
    elif profile == "compile-ready":
        _validate_compile_ready_profile(elements, result, profile)
    elif profile == "erc-ready":
        _validate_compile_ready_profile(elements, result, profile)
        _validate_erc_ready_profile(result, profile)


def _validate_schematic_profile(
    elements: list[CircuitElement],
    context: dict[str, Any],
    result: ValidationResult,
    profile: str,
) -> None:
    source_components = context["source_components"]
    source_ports = context["source_ports"]
    schematic_ids: set[str] = set()

    for element in elements:
        if isinstance(element, SchematicComponent):
            if element.schematic_component_id in schematic_ids:
                result.add_error(
                    "schematic_unique_ids",
                    f"Duplicate schematic element ID: {element.schematic_component_id}",
                    element_id=element.schematic_component_id,
                    profile=profile,
                )
            schematic_ids.add(element.schematic_component_id)
            if element.source_component_id not in source_components:
                result.add_error(
                    "schematic_reference",
                    f"Schematic component references missing source_component: {element.source_component_id}",
                    element_id=element.schematic_component_id,
                    profile=profile,
                )
            if element.center is None:
                result.add_error(
                    "schematic_geometry",
                    "Schematic component must have a center position.",
                    element_id=element.schematic_component_id,
                    profile=profile,
                )
        elif isinstance(element, SchematicPort):
            if element.schematic_port_id in schematic_ids:
                result.add_error(
                    "schematic_unique_ids",
                    f"Duplicate schematic element ID: {element.schematic_port_id}",
                    element_id=element.schematic_port_id,
                    profile=profile,
                )
            schematic_ids.add(element.schematic_port_id)
            if element.source_port_id not in source_ports:
                result.add_error(
                    "schematic_reference",
                    f"Schematic port references missing source_port: {element.source_port_id}",
                    element_id=element.schematic_port_id,
                    profile=profile,
                )
        elif isinstance(element, SchematicTrace):
            if element.schematic_trace_id in schematic_ids:
                result.add_error(
                    "schematic_unique_ids",
                    f"Duplicate schematic element ID: {element.schematic_trace_id}",
                    element_id=element.schematic_trace_id,
                    profile=profile,
                )
            schematic_ids.add(element.schematic_trace_id)
            if not element.edges:
                result.add_error(
                    "schematic_geometry",
                    "Schematic trace must contain at least one edge.",
                    element_id=element.schematic_trace_id,
                    profile=profile,
                )
        elif isinstance(element, SchematicNetLabel) and not element.text:
            result.add_error("schematic_label", "Schematic label text must not be empty.", profile=profile)
        elif isinstance(element, SchematicNoConnect) and element.position is None:
            result.add_error("schematic_no_connect", "No-connect marker must have a position.", profile=profile)


def _validate_compile_ready_profile(
    elements: list[CircuitElement],
    result: ValidationResult,
    profile: str,
) -> None:
    source_components = [e for e in elements if isinstance(e, SourceComponent)]
    if not source_components:
        result.add_error(
            "compile_ready_source",
            "At least one source component is required to generate KiCad files.",
            profile=profile,
        )
    for component in source_components:
        if not component.symbol_id and not component.ftype:
            result.add_warning(
                "compile_ready_symbol",
                f"Component {component.source_component_id} has no symbol_id or ftype; fallback symbols may be used.",
                element_id=component.source_component_id,
                profile=profile,
            )


def _validate_erc_ready_profile(result: ValidationResult, profile: str) -> None:
    from circuitweaver.library.paths import find_kicad_cli

    if find_kicad_cli() is None:
        result.add_error(
            "erc_ready_kicad_cli",
            "kicad-cli is required for ERC but was not found.",
            profile=profile,
        )


def _build_validation_context(elements: list[CircuitElement]) -> dict[str, Any]:
    """Build a context dictionary for validation rules."""
    source_components: dict[str, SourceComponent] = {}
    source_ports: dict[str, SourcePort] = {}
    source_nets: dict[str, SourceNet] = {}
    source_traces: dict[str, SourceTrace] = {}
    source_groups: dict[str, SourceGroup] = {}
    schematic_components: dict[str, SchematicComponent] = {}
    schematic_ports: dict[str, SchematicPort] = {}
    schematic_traces: dict[str, SchematicTrace] = {}

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
        elif isinstance(element, SchematicComponent):
            schematic_components[element.schematic_component_id] = element
        elif isinstance(element, SchematicPort):
            schematic_ports[element.schematic_port_id] = element
        elif isinstance(element, SchematicTrace):
            schematic_traces[element.schematic_trace_id] = element

    return {
        "source_components": source_components,
        "source_ports": source_ports,
        "source_nets": source_nets,
        "source_traces": source_traces,
        "source_groups": source_groups,
        "schematic_components": schematic_components,
        "schematic_ports": schematic_ports,
        "schematic_traces": schematic_traces,
        "subcircuit_ids": subcircuit_ids,
        "elements": elements,
    }

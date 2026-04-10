"""JSON I/O for Circuit elements and Layout graphs.

Handles reading and writing of:
- Source elements (logical netlist)
- Layout elements (ELK graph)
- Schematic elements (visual layout)
- Combined circuit files (Source + Schematic)
"""

import json
from pathlib import Path
from typing import Any, List, Type

from circuitweaver.types import (
    CircuitElement,
    LayoutNode,
    SchematicBox,
    SchematicComponent,
    SchematicHierarchicalLabel,
    SchematicHierarchicalPin,
    SchematicNetLabel,
    SchematicNoConnect,
    SchematicPort,
    SchematicText,
    SchematicTrace,
    SourceComponent,
    SourceGroup,
    SourceNet,
    SourcePort,
    SourceTrace,
)


# =============================================================================
# Type Mappings
# =============================================================================

SOURCE_TYPE_MAP: dict[str, Type[CircuitElement]] = {
    "source_component": SourceComponent,
    "source_port": SourcePort,
    "source_net": SourceNet,
    "source_trace": SourceTrace,
    "source_group": SourceGroup,
}

SCHEMATIC_TYPE_MAP: dict[str, Type[CircuitElement]] = {
    "schematic_component": SchematicComponent,
    "schematic_port": SchematicPort,
    "schematic_trace": SchematicTrace,
    "schematic_box": SchematicBox,
    "schematic_net_label": SchematicNetLabel,
    "schematic_hierarchical_pin": SchematicHierarchicalPin,
    "schematic_hierarchical_label": SchematicHierarchicalLabel,
    "schematic_text": SchematicText,
    "schematic_no_connect": SchematicNoConnect,
}

ELEMENT_TYPE_MAP: dict[str, Type[CircuitElement]] = {
    **SOURCE_TYPE_MAP,
    **SCHEMATIC_TYPE_MAP,
}


# =============================================================================
# Circuit I/O (Source + Schematic combined)
# =============================================================================

def read_circuit(file_path: Path) -> List[CircuitElement]:
    """Read a Circuit JSON file containing Source and/or Schematic elements.

    Args:
        file_path: Path to the JSON file.

    Returns:
        List of parsed CircuitElement instances.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        json.JSONDecodeError: If the file contains invalid JSON.
        ValueError: If the file structure is invalid.
    """
    with open(file_path) as f:
        raw_data = json.load(f)

    if not isinstance(raw_data, list):
        raise ValueError(
            f"Circuit JSON must be a list of elements, got {type(raw_data).__name__}"
        )

    return _parse_elements(raw_data, ELEMENT_TYPE_MAP)


def write_circuit(
    file_path: Path,
    elements: List[CircuitElement],
    indent: int = 2,
) -> None:
    """Write circuit elements to a JSON file.

    Args:
        file_path: Path to save the JSON file.
        elements: List of CircuitElement instances.
        indent: JSON indentation level.
    """
    data = [e.model_dump(mode="json", by_alias=True) for e in elements]
    with open(file_path, "w") as f:
        json.dump(data, f, indent=indent)


# =============================================================================
# Source I/O
# =============================================================================

def read_source(file_path: Path) -> List[CircuitElement]:
    """Read a JSON file containing only Source elements.

    Args:
        file_path: Path to the JSON file.

    Returns:
        List of Source elements (SourceComponent, SourcePort, etc.).

    Raises:
        ValueError: If file contains non-source elements.
    """
    with open(file_path) as f:
        raw_data = json.load(f)

    if not isinstance(raw_data, list):
        raise ValueError(f"JSON must be a list of elements, got {type(raw_data).__name__}")

    return _parse_elements(raw_data, SOURCE_TYPE_MAP)


def write_source(
    file_path: Path,
    elements: List[CircuitElement],
    indent: int = 2,
) -> None:
    """Write Source elements to a JSON file.

    Args:
        file_path: Path to save the JSON file.
        elements: List of elements (only source_* types will be saved).
        indent: JSON indentation level.
    """
    source_elements = [e for e in elements if e.type.startswith("source_")]
    data = [e.model_dump(mode="json", by_alias=True) for e in source_elements]
    with open(file_path, "w") as f:
        json.dump(data, f, indent=indent)


# =============================================================================
# Schematic I/O
# =============================================================================

def read_schematic(file_path: Path) -> List[CircuitElement]:
    """Read a JSON file containing only Schematic elements.

    Args:
        file_path: Path to the JSON file.

    Returns:
        List of Schematic elements (SchematicComponent, SchematicPort, etc.).

    Raises:
        ValueError: If file contains non-schematic elements.
    """
    with open(file_path) as f:
        raw_data = json.load(f)

    if not isinstance(raw_data, list):
        raise ValueError(f"JSON must be a list of elements, got {type(raw_data).__name__}")

    return _parse_elements(raw_data, SCHEMATIC_TYPE_MAP)


def write_schematic(
    file_path: Path,
    elements: List[CircuitElement],
    indent: int = 2,
) -> None:
    """Write Schematic elements to a JSON file.

    Args:
        file_path: Path to save the JSON file.
        elements: List of elements (only schematic_* types will be saved).
        indent: JSON indentation level.
    """
    schematic_elements = [e for e in elements if e.type.startswith("schematic_")]
    data = [e.model_dump(mode="json", by_alias=True) for e in schematic_elements]
    with open(file_path, "w") as f:
        json.dump(data, f, indent=indent)


# =============================================================================
# Layout I/O (ELK graph)
# =============================================================================

def read_layout(file_path: Path) -> LayoutNode:
    """Read a Layout JSON file into a LayoutNode graph.

    Args:
        file_path: Path to the JSON file.

    Returns:
        Root LayoutNode with children, ports, edges, etc.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        json.JSONDecodeError: If the file contains invalid JSON.
        pydantic.ValidationError: If the structure doesn't match LayoutNode.
    """
    with open(file_path) as f:
        raw_data = json.load(f)

    return LayoutNode.model_validate(raw_data)


def write_layout(
    file_path: Path,
    layout: LayoutNode,
    indent: int = 2,
) -> None:
    """Write a LayoutNode graph to a JSON file.

    Args:
        file_path: Path to save the JSON file.
        layout: Root LayoutNode to save.
        indent: JSON indentation level.
    """
    data = layout.model_dump(mode="json")
    with open(file_path, "w") as f:
        json.dump(data, f, indent=indent)


# =============================================================================
# Element Parsing Helpers
# =============================================================================

def parse_element(raw: dict[str, Any]) -> CircuitElement:
    """Parse a raw dictionary into a typed CircuitElement.

    Args:
        raw: Raw element dictionary with a 'type' field.

    Returns:
        Parsed CircuitElement instance.

    Raises:
        ValueError: If the element type is unknown or missing.
    """
    element_type = raw.get("type")

    if element_type is None:
        raise ValueError("Element missing 'type' field")

    if element_type not in ELEMENT_TYPE_MAP:
        valid_types = ", ".join(sorted(ELEMENT_TYPE_MAP.keys()))
        raise ValueError(
            f"Unknown element type: '{element_type}'. Valid types are: {valid_types}."
        )

    return ELEMENT_TYPE_MAP[element_type].model_validate(raw)


def _parse_elements(
    raw_elements: List[dict[str, Any]],
    type_map: dict[str, Type[CircuitElement]],
) -> List[CircuitElement]:
    """Parse a list of raw dictionaries into typed elements.

    Args:
        raw_elements: List of raw element dictionaries.
        type_map: Mapping from type string to element class.

    Returns:
        List of parsed CircuitElement instances.

    Raises:
        ValueError: If any element is invalid.
    """
    elements: List[CircuitElement] = []

    for i, raw in enumerate(raw_elements):
        if not isinstance(raw, dict):
            raise ValueError(
                f"Element {i} must be an object, got {type(raw).__name__}"
            )

        element_type = raw.get("type")
        if element_type is None:
            raise ValueError(f"Element {i} missing 'type' field")

        if element_type not in type_map:
            valid_types = ", ".join(sorted(type_map.keys()))
            raise ValueError(
                f"Element {i}: Unknown type '{element_type}'. Valid types are: {valid_types}."
            )

        elements.append(type_map[element_type].model_validate(raw))

    return elements


def get_element_id_from_raw(raw: dict[str, Any]) -> str | None:
    """Extract element ID from a raw dictionary.

    Useful for error reporting when parsing fails.

    Args:
        raw: Raw element dictionary.

    Returns:
        The element ID if found, None otherwise.
    """
    id_fields = [
        "source_component_id",
        "source_port_id",
        "source_net_id",
        "source_trace_id",
        "source_group_id",
        "schematic_component_id",
        "schematic_port_id",
        "schematic_trace_id",
        "schematic_box_id",
        "schematic_net_label_id",
        "schematic_hierarchical_pin_id",
        "schematic_hierarchical_label_id",
        "schematic_text_id",
        "schematic_no_connect_id",
    ]

    for key in id_fields:
        if key in raw:
            return raw[key]

    return None

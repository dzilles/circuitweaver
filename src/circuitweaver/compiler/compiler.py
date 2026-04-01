"""Main compiler for Circuit JSON to KiCad schematic."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from circuitweaver.compiler.kicad_writer import KiCadWriter
from circuitweaver.types.circuit_json import (
    CircuitElement,
    SchematicBox,
    SchematicComponent,
    SchematicNetLabel,
    SchematicPort,
    SchematicSheet,
    SchematicText,
    SchematicTrace,
    SourceComponent,
)
from circuitweaver.types.errors import CompilationError

logger = logging.getLogger(__name__)


def compile_to_kicad(input_file: Path, output_dir: Path) -> List[Path]:
    """Compile Circuit JSON to KiCad schematic files."""
    try:
        with open(input_file) as f:
            raw_data = json.load(f)
    except Exception as e:
        raise CompilationError(f"Failed to load Circuit JSON: {e}", phase="load")

    if not isinstance(raw_data, list):
        raise CompilationError("Circuit JSON must be a list of elements", phase="load")

    # Parse elements
    elements = _parse_elements(raw_data)

    # Initialize stateful compiler context
    compiler = CircuitCompiler()
    compiler.load(elements)

    # Group elements by sheet
    sheets = _group_by_sheet(elements)

    # Generate KiCad files
    output_files: List[Path] = []
    writer = KiCadWriter()
    project_name = input_file.stem

    for sheet_id, sheet_elements in sheets.items():
        # Use project name for root sheet to match project file references
        sheet_name = sheet_id or project_name
        output_file = output_dir / f"{sheet_name}.kicad_sch"

        # Pass global source_components for resolution
        content = writer.write_schematic(sheet_elements, sheet_name, compiler.source_components)
        output_file.write_text(content)
        output_files.append(output_file)

        logger.info(f"Generated {output_file}")

    # Always generate project file
    project_file = output_dir / f"{project_name}.kicad_pro"
    project_content = writer.write_project(project_name, list(sheets.keys()))
    project_file.write_text(project_content)
    output_files.append(project_file)

    # Warn about orphan schematics in output directory
    generated_names = {f.name for f in output_files if f.suffix == ".kicad_sch"}
    for sch_file in output_dir.glob("*.kicad_sch"):
        if sch_file.name not in generated_names:
            logger.warning(
                f"Existing schematic '{sch_file.name}' is not part of this project. "
                f"Consider removing it to avoid confusion."
            )

    return output_files


def _parse_elements(raw_data: List[Dict[str, Any]]) -> List[CircuitElement]:
    """Parse raw JSON into typed elements."""
    from circuitweaver.validator.engine import _parse_element

    elements: List[CircuitElement] = []
    for raw in raw_data:
        try:
            elements.append(_parse_element(raw))
        except Exception as e:
            logger.warning(f"Failed to parse element: {e}")
            continue

    return elements


def _group_by_sheet(
    elements: List[CircuitElement],
) -> Dict[Optional[str], List[CircuitElement]]:
    """Group elements by their sheet ID."""
    # For now, put everything in one sheet
    # In the future, we can look for schematic_sheet_id on elements
    return {None: elements}


class CircuitCompiler:
    """Stateful compiler for Circuit JSON to KiCad."""

    def __init__(self) -> None:
        self.source_components: Dict[str, SourceComponent] = {}
        self.schematic_components: Dict[str, SchematicComponent] = {}
        self.traces: List[SchematicTrace] = []
        self.boxes: List[SchematicBox] = []
        self.labels: List[SchematicNetLabel] = []
        self.texts: List[SchematicText] = []
        self.ports: Dict[str, SchematicPort] = {}

    def load(self, elements: List[CircuitElement]) -> None:
        """Load and index elements."""
        for element in elements:
            if isinstance(element, SourceComponent):
                self.source_components[element.source_component_id] = element
            elif isinstance(element, SchematicComponent):
                self.schematic_components[element.schematic_component_id] = element
            elif isinstance(element, SchematicTrace):
                self.traces.append(element)
            elif isinstance(element, SchematicBox):
                self.boxes.append(element)
            elif isinstance(element, SchematicNetLabel):
                self.labels.append(element)
            elif isinstance(element, SchematicText):
                self.texts.append(element)
            elif isinstance(element, SchematicPort):
                self.ports[element.schematic_port_id] = element

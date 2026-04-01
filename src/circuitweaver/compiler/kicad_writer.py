"""KiCad schematic file writer."""

import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from circuitweaver.library.pinout import get_expanded_symbol_definition
from circuitweaver.types.circuit_json import (
    CircuitElement,
    SchematicBox,
    SchematicComponent,
    SchematicNetLabel,
    SchematicNoConnect,
    SchematicPort,
    SchematicText,
    SchematicTrace,
    SourceComponent,
)

logger = logging.getLogger(__name__)

# Grid unit to mm conversion (1 grid = 0.127mm = 5mil)
GRID_TO_MM = 0.127


class KiCadWriter:
    """Writer for KiCad schematic files (.kicad_sch)."""

    def __init__(self) -> None:
        self.uuid_counter = 0

    def _new_uuid(self) -> str:
        """Generate a new UUID for KiCad elements."""
        return str(uuid.uuid4())

    def _grid_to_mm(self, grid: int) -> float:
        """Convert grid units to millimeters."""
        return grid * GRID_TO_MM

    def write_schematic(
        self, 
        elements: List[CircuitElement], 
        sheet_name: str,
        source_components: Dict[str, SourceComponent]
    ) -> str:
        """Write a KiCad schematic file."""
        lines = [
            "(kicad_sch",
            "\t(version 20260306)",
            '\t(generator "eeschema")',
            '\t(generator_version "10.0")',
            f'\t(uuid "{self._new_uuid()}")',
            '\t(paper "A4")',
            "\t(lib_symbols",
        ]

        # Filter schematic components on this sheet
        schematic_components = [
            e for e in elements if isinstance(e, SchematicComponent)
        ]

        # Collect and embed symbol definitions (fully expanded, no extends)
        symbols_needed, lib_id_to_lib_name = self._collect_symbols_recursive(
            schematic_components, source_components
        )
        for symbol_def in symbols_needed:
            lines.append(symbol_def)

        lines.append("\t)")  # Close lib_symbols
        lines.append("")

        # Add components
        for comp in schematic_components:
            comp_lines = self._write_component(comp, source_components, lib_id_to_lib_name)
            lines.extend(comp_lines)

        # Add wires (traces)
        for element in elements:
            if isinstance(element, SchematicTrace):
                wire_lines = self._write_trace(element)
                lines.extend(wire_lines)

        # Add labels
        for element in elements:
            if isinstance(element, SchematicNetLabel):
                label_lines = self._write_label(element)
                lines.extend(label_lines)

        # Add text annotations
        for element in elements:
            if isinstance(element, SchematicText):
                text_lines = self._write_text(element)
                lines.extend(text_lines)

        # Add graphic boxes
        for element in elements:
            if isinstance(element, SchematicBox):
                box_lines = self._write_box(element)
                lines.extend(box_lines)

        # Add no-connect flags
        # First, build a port lookup for position
        ports: Dict[str, SchematicPort] = {
            e.schematic_port_id: e for e in elements if isinstance(e, SchematicPort)
        }
        for element in elements:
            if isinstance(element, SchematicNoConnect):
                nc_lines = self._write_no_connect(element, ports)
                lines.extend(nc_lines)

        lines.append(")")  # Close kicad_sch

        return "\n".join(lines)

    def _resolve_lib_id(self, comp: SchematicComponent, source: Optional[SourceComponent]) -> str:
        """Strictly resolve a component to a KiCad library:symbol ID."""
        if comp.symbol_name and ":" in comp.symbol_name:
            return comp.symbol_name
        if ":" in comp.source_component_id:
            return comp.source_component_id
        if source and source.value and ":" in source.value:
            return source.value
        ref = source.name if source else comp.schematic_component_id
        return f"ERROR:MISSING_LIB_ID_FOR_{ref}"

    def _collect_symbols_recursive(
        self,
        components: List[SchematicComponent],
        sources: Dict[str, SourceComponent],
    ) -> Tuple[List[str], Dict[str, str]]:
        """Collect and generate lib_symbol definitions (fully expanded, no extends).

        KiCad 10 requires symbols to be fully expanded in lib_symbols.
        Returns (list of symbol definitions, mapping of lib_id to lib_name).
        """
        embedded_defs: Dict[str, str] = {}
        lib_id_to_lib_name: Dict[str, str] = {}  # Maps "Lib:Sym" to "Sym_1"
        processed_keys: Set[str] = set()
        symbol_counter: Dict[str, int] = {}  # Track suffix numbers per symbol name

        for comp in components:
            source = sources.get(comp.source_component_id)
            lib_id = self._resolve_lib_id(comp, source)

            if lib_id.startswith("ERROR:") or lib_id.startswith("hierarchy:"):
                continue
            if lib_id in processed_keys:
                continue
            processed_keys.add(lib_id)

            lib_name, sym_name = lib_id.split(":", 1)

            # Generate unique lib_name: "SymbolName_1", "SymbolName_2", etc.
            if sym_name not in symbol_counter:
                symbol_counter[sym_name] = 1
            else:
                symbol_counter[sym_name] += 1
            embedded_name = f"{sym_name}_{symbol_counter[sym_name]}"
            lib_id_to_lib_name[lib_id] = embedded_name

            try:
                # Get fully expanded symbol (no extends)
                symbol_def = get_expanded_symbol_definition(
                    sym_name, library_name=lib_name, rename_to=embedded_name
                )
                embedded_defs[embedded_name] = self._indent_sexp(symbol_def, indent=2)

            except ValueError as e:
                logger.warning(f"Could not embed symbol '{sym_name}' from library '{lib_name}': {e}")

        # Return sorted by key to ensure deterministic output
        return ([embedded_defs[k] for k in sorted(embedded_defs.keys())], lib_id_to_lib_name)

    def _indent_sexp(self, sexp: str, indent: int = 4) -> str:
        prefix = " " * indent
        lines = sexp.split("\n")
        return "\n".join(prefix + line if line.strip() else line for line in lines)

    def _write_component(
        self,
        comp: SchematicComponent,
        sources: Dict[str, SourceComponent],
        lib_id_to_lib_name: Dict[str, str],
    ) -> List[str]:
        """Write a symbol instance."""
        lines: List[str] = []

        source = sources.get(comp.source_component_id)
        lib_id = self._resolve_lib_id(comp, source)
        lib_name = lib_id_to_lib_name.get(lib_id, lib_id)

        if source:
            reference = source.name
            value = source.value or ""
        else:
            reference = "U?"
            value = ""

        x_mm = self._grid_to_mm(comp.center.x)
        y_mm = self._grid_to_mm(comp.center.y)
        angle = comp.rotation
        comp_uuid = self._new_uuid()

        lines.append("")
        lines.append("\t(symbol")
        lines.append(f'\t\t(lib_name "{lib_name}")')
        lines.append(f'\t\t(lib_id "{lib_id}")')
        lines.append(f"\t\t(at {x_mm:.2f} {y_mm:.2f} {angle})")
        lines.append("\t\t(unit 1)")
        lines.append("\t\t(exclude_from_sim no)")
        lines.append("\t\t(in_bom yes)")
        lines.append("\t\t(on_board yes)")
        lines.append("\t\t(dnp no)")
        lines.append(f'\t\t(uuid "{comp_uuid}")')

        # Properties
        lines.append(f'\t\t(property "Reference" "{reference}"')
        lines.append(f"\t\t\t(at {x_mm:.2f} {y_mm - 2.54:.2f} 0)")
        lines.append("\t\t\t(effects (font (size 1.27 1.27)))")
        lines.append("\t\t)")

        lines.append(f'\t\t(property "Value" "{value}"')
        lines.append(f"\t\t\t(at {x_mm:.2f} {y_mm + 2.54:.2f} 0)")
        lines.append("\t\t\t(effects (font (size 1.27 1.27)))")
        lines.append("\t\t)")

        if source and source.footprint:
            lines.append(f'\t\t(property "Footprint" "{source.footprint}"')
            lines.append(f"\t\t\t(at {x_mm:.2f} {y_mm:.2f} 0)")
            lines.append("\t\t\t(hide yes)")
            lines.append("\t\t\t(effects (font (size 1.27 1.27)))")
            lines.append("\t\t)")
        else:
            lines.append('\t\t(property "Footprint" ""')
            lines.append(f"\t\t\t(at {x_mm:.2f} {y_mm:.2f} 0)")
            lines.append("\t\t\t(hide yes)")
            lines.append("\t\t\t(effects (font (size 1.27 1.27)))")
            lines.append("\t\t)")

        lines.append("\t)")

        return lines

    def _write_trace(self, trace: SchematicTrace) -> List[str]:
        """Write wire segments for a trace."""
        lines: List[str] = []

        for edge in trace.edges:
            x1 = self._grid_to_mm(edge.from_.x)
            y1 = self._grid_to_mm(edge.from_.y)
            x2 = self._grid_to_mm(edge.to.x)
            y2 = self._grid_to_mm(edge.to.y)

            lines.append("")
            lines.append(f'  (wire')
            lines.append(f'    (pts')
            lines.append(f'      (xy {x1:.2f} {y1:.2f})')
            lines.append(f'      (xy {x2:.2f} {y2:.2f})')
            lines.append(f'    )')
            lines.append(f'    (stroke (width 0) (type default))')
            lines.append(f'    (uuid "{self._new_uuid()}")')
            lines.append(f'  )')

        return lines

    def _write_label(self, label: SchematicNetLabel) -> List[str]:
        x_mm = self._grid_to_mm(label.center.x)
        y_mm = self._grid_to_mm(label.center.y)
        angle_map = {"right": 0, "top": 90, "left": 180, "bottom": 270}
        angle = angle_map.get(label.anchor_side, 0)

        return [
            "",
            f'  (label "{label.text}"',
            f'    (at {x_mm:.2f} {y_mm:.2f} {angle})',
            f'    (effects (font (size 1.27 1.27)) (justify left))',
            f'    (uuid "{self._new_uuid()}")',
            f'  )',
        ]

    def _write_text(self, text: SchematicText) -> List[str]:
        x_mm = self._grid_to_mm(text.position.x)
        y_mm = self._grid_to_mm(text.position.y)
        escaped_text = text.text.replace("\n", "\\n")

        return [
            "",
            f'  (text "{escaped_text}"',
            f'    (at {x_mm:.2f} {y_mm:.2f} {text.rotation})',
            f'    (effects (font (size 1.27 1.27)) (justify left))',
            f'    (uuid "{self._new_uuid()}")',
            f'  )',
        ]

    def _write_box(self, box: SchematicBox) -> List[str]:
        x1 = self._grid_to_mm(box.x)
        y1 = self._grid_to_mm(box.y)
        x2 = self._grid_to_mm(box.x + box.width)
        y2 = self._grid_to_mm(box.y + box.height)

        return [
            "",
            f'  (rectangle',
            f'    (start {x1:.2f} {y1:.2f})',
            f'    (end {x2:.2f} {y2:.2f})',
            f'    (stroke (width 0.1524) (type default))',
            f'    (fill (type none))',
            f'    (uuid "{self._new_uuid()}")',
            f'  )',
        ]

    def _write_no_connect(
        self, nc: SchematicNoConnect, ports: Dict[str, SchematicPort]
    ) -> List[str]:
        """Write a no-connect flag.

        KiCad format:
        (no_connect
            (at x y)
            (uuid "...")
        )
        """
        # Use position from the no-connect element, or fall back to port position
        if nc.schematic_port_id in ports:
            port = ports[nc.schematic_port_id]
            x_mm = self._grid_to_mm(port.center.x)
            y_mm = self._grid_to_mm(port.center.y)
        else:
            x_mm = self._grid_to_mm(nc.position.x)
            y_mm = self._grid_to_mm(nc.position.y)

        return [
            "",
            "\t(no_connect",
            f"\t\t(at {x_mm:.2f} {y_mm:.2f})",
            f'\t\t(uuid "{self._new_uuid()}")',
            "\t)",
        ]

    def write_project(self, project_name: str, sheet_names: List[Optional[str]]) -> str:
        return f'''{{
  "meta": {{
    "filename": "{project_name}.kicad_pro",
    "version": 3
  }},
  "schematic": {{
    "legacy_lib_dir": "",
    "legacy_lib_list": []
  }},
  "boards": [],
  "sheets": [
    [
      "Root",
      "{project_name}.kicad_sch"
    ]
  ]
}}'''

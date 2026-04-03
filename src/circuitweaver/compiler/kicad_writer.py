"""KiCad schematic file writer with multi-sheet support."""

import logging
import re
import uuid
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Set, Tuple

from circuitweaver.library.pinout import get_expanded_symbol_definition
from circuitweaver.types.circuit_json import (
    CircuitElement,
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
)

logger = logging.getLogger(__name__)

# Grid unit to mm conversion (1 grid = 5mil = 0.127mm)
GRID_TO_MM = Decimal('0.127')


class KiCadWriter:
    """Writer for KiCad schematic files (.kicad_sch)."""

    def __init__(self) -> None:
        pass

    def _new_uuid(self) -> str:
        """Generate a new UUID for KiCad elements."""
        return str(uuid.uuid4())

    def _grid_to_mm(self, grid: float) -> str:
        """Convert grid units to millimeters with strict rounding."""
        val = Decimal(str(grid)).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * GRID_TO_MM
        return "{:.4f}".format(val)

    def write_schematic(
        self, 
        elements: List[CircuitElement], 
        sheet_id: str,
        source_components: Dict[str, SourceComponent]
    ) -> str:
        """Write a KiCad schematic file for a specific sheet."""
        sheet_elements = [
            e for e in elements 
            if not hasattr(e, "sheet_id") or e.sheet_id == sheet_id
        ]

        lines = [
            "(kicad_sch",
            "  (version 20260306)",
            '  (generator "eeschema")',
            '  (generator_version "10.0")',
            f'  (uuid "{self._new_uuid()}")',
            '  (paper "A4")',
        ]

        sheet_components = [e for e in sheet_elements if isinstance(e, SchematicComponent)]
        sheet_pins = [e for e in sheet_elements if isinstance(e, SchematicHierarchicalPin)]
        sheet_h_labels = [e for e in sheet_elements if isinstance(e, SchematicHierarchicalLabel)]
        sheet_net_labels = [e for e in sheet_elements if isinstance(e, SchematicNetLabel)]
        sheet_no_connects = [e for e in sheet_elements if isinstance(e, SchematicNoConnect)]
        
        # 1. Symbol Library definitions
        lines.append("  (lib_symbols")
        if sheet_components:
            symbols_needed, lib_id_to_lib_name = self._collect_symbols_recursive(
                sheet_components, source_components
            )
            for symbol_def in symbols_needed:
                lines.append(symbol_def)
        else:
            lib_id_to_lib_name = {}
        lines.append("  )")

        # 2. Hierarchical Sheets (Boxes)
        sheet_boxes = [e for e in sheet_elements if isinstance(e, SchematicBox) and e.is_hierarchical_sheet]
        for box in sheet_boxes:
            pins = [p for p in sheet_pins if p.schematic_box_id == box.schematic_box_id]
            lines.extend(self._write_hierarchical_sheet(box, pins))

        # 3. Component Instances
        for comp in sheet_components:
            lines.extend(self._write_component(comp, source_components, lib_id_to_lib_name))

        # 4. Traces & Junctions
        point_counts = defaultdict(int)
        for element in sheet_elements:
            if isinstance(element, SchematicTrace):
                lines.extend(self._write_trace(element))
                for edge in element.edges:
                    point_counts[(int(round(edge.from_.x)), int(round(edge.from_.y)))] += 1
                    point_counts[(int(round(edge.to.x)), int(round(edge.to.y)))] += 1
        
        for pin in sheet_pins:
            point_counts[(int(round(pin.center.x)), int(round(pin.center.y)))] += 1
        for lbl in sheet_h_labels:
            point_counts[(int(round(lbl.center.x)), int(round(lbl.center.y)))] += 1
        for lbl in sheet_net_labels:
            point_counts[(int(round(lbl.center.x)), int(round(lbl.center.y)))] += 1

        for (gx, gy), count in point_counts.items():
            if count >= 3:
                x_mm = self._grid_to_mm(gx)
                y_mm = self._grid_to_mm(gy)
                lines.append(f'  (junction (at {x_mm} {y_mm}) (uuid "{self._new_uuid()}"))')

        # 5. Labels & Text & No-Connects
        for element in sheet_elements:
            if isinstance(element, SchematicNetLabel):
                lines.extend(self._write_label(element))
            elif isinstance(element, SchematicHierarchicalLabel):
                lines.extend(self._write_hierarchical_label(element))
            elif isinstance(element, SchematicText):
                lines.extend(self._write_text(element))
            elif isinstance(element, SchematicNoConnect):
                lines.extend(self._write_no_connect(element))

        # 6. Graphic Boxes
        for element in sheet_elements:
            if isinstance(element, SchematicBox) and not element.is_hierarchical_sheet:
                lines.extend(self._write_box(element))

        lines.append("  (sheet_instances")
        lines.append(f'    (path "/" (page "1"))')
        lines.append("  )")
        lines.append("  (embedded_fonts no)")
        lines.append(")")

        return "\n".join(lines)

    def _write_no_connect(self, nc: SchematicNoConnect) -> List[str]:
        if not nc.position: return []
        x = self._grid_to_mm(nc.position.x)
        y = self._grid_to_mm(nc.position.y)
        return [f'  (no_connect (at {x} {y}) (uuid "{self._new_uuid()}"))']

    def _write_hierarchical_sheet(self, box: SchematicBox, pins: List[SchematicHierarchicalPin]) -> List[str]:
        x = self._grid_to_mm(box.x); y = self._grid_to_mm(box.y)
        w = self._grid_to_mm(box.width); h = self._grid_to_mm(box.height)
        sheet_name = box.name or box.schematic_box_id
        file_name = f"{box.schematic_box_id.replace('box_', '')}.kicad_sch"
        
        nx_mm = self._grid_to_mm(box.x + box.name_offset.x)
        ny_mm = self._grid_to_mm(box.y + box.name_offset.y)
        fx_mm = self._grid_to_mm(box.x + box.file_offset.x)
        fy_mm = self._grid_to_mm(box.y + box.file_offset.y)
        
        lines = [
            f'  (sheet (at {x} {y}) (size {w} {h})',
            '    (fields_autoplaced yes)',
            '    (stroke (width 0.1524) (type solid))',
            '    (fill (color 0 0 0 0))',
            f'    (uuid "{self._new_uuid()}")',
            f'    (property "Sheetname" "{sheet_name}" (at {nx_mm} {ny_mm} 0) (effects (font (size 1.27 1.27)) (justify left top)))',
            f'    (property "Sheetfile" "{file_name}" (at {fx_mm} {fy_mm} 0) (effects (font (size 1.27 1.27)) (justify left top)))'
        ]
        for pin in pins:
            px = self._grid_to_mm(pin.center.x)
            py = self._grid_to_mm(pin.center.y)
            justify = "left" if int(round(pin.center.x)) <= int(round(box.x)) else "right"
            angle = 180 if int(round(pin.center.x)) <= int(round(box.x)) else 0
            lines.append(f'    (pin "{pin.text}" input (at {px} {py} {angle}) (uuid "{self._new_uuid()}") (effects (font (size 1.27 1.27)) (justify {justify})))')
        lines.append('  )')
        return lines

    def _write_hierarchical_label(self, label: SchematicHierarchicalLabel) -> List[str]:
        x = self._grid_to_mm(label.center.x); y = self._grid_to_mm(label.center.y)
        # Use angle AND justification for sub-sheet hierarchical labels
        angle = {"right": 0, "top": 90, "left": 180, "bottom": 270}.get(label.anchor_side, 0)
        justify = label.anchor_side
        return [f'  (hierarchical_label "{label.text}" (shape input) (at {x} {y} {angle}) (effects (font (size 1.27 1.27)) (justify {justify})) (uuid "{self._new_uuid()}"))']

    def _resolve_lib_id(self, comp: SchematicComponent, source: Optional[SourceComponent]) -> str:
        if comp.symbol_name and ":" in comp.symbol_name: return comp.symbol_name
        if source and source.symbol_id: return source.symbol_id
        return f"Device:QuestionBlock"

    def _collect_symbols_recursive(self, components: List[SchematicComponent], sources: Dict[str, SourceComponent]) -> Tuple[List[str], Dict[str, str]]:
        embedded_defs = {}; lib_id_to_lib_name = {}; processed = set(); counter = 0
        for comp in components:
            source = sources.get(comp.source_component_id)
            lib_id = self._resolve_lib_id(comp, source)
            if lib_id.startswith("ERROR:") or lib_id.startswith("hierarchy:") or lib_id in processed: continue
            processed.add(lib_id)
            lib_parts = lib_id.split(":", 1)
            if len(lib_parts) < 2: continue
            lib_name, sym_name = lib_parts
            counter += 1
            embedded_name = f"Sym_{counter}"
            lib_id_to_lib_name[lib_id] = embedded_name
            try:
                symbol_def = get_expanded_symbol_definition(sym_name, library_name=lib_name, rename_to=embedded_name)
                embedded_defs[embedded_name] = self._indent_sexp(symbol_def, indent=4)
            except Exception as e: logger.warning(f"Could not embed {lib_id}: {e}")
        return ([embedded_defs[k] for k in sorted(embedded_defs.keys())], lib_id_to_lib_name)

    def _indent_sexp(self, sexp: str, indent: int = 4) -> str:
        prefix = " " * indent
        return "\n".join(prefix + line if line.strip() else line for line in sexp.split("\n"))

    def _write_component(self, comp: SchematicComponent, sources: Dict[str, SourceComponent], lib_id_to_lib_name: Dict[str, str]) -> List[str]:
        source = sources.get(comp.source_component_id)
        lib_id = self._resolve_lib_id(comp, source)
        lib_name = lib_id_to_lib_name.get(lib_id, lib_id)
        ref = source.name if source else "U?"
        val = source.display_value if source and source.display_value else (source.symbol_id if source else "")
        x = self._grid_to_mm(comp.center.x); y = self._grid_to_mm(comp.center.y)
        lines = [
            f'  (symbol (lib_name "{lib_name}") (lib_id "{lib_id}") (at {x} {y} {comp.rotation}) (unit 1) (uuid "{self._new_uuid()}")',
            f'    (property "Reference" "{ref}" (at {x} {self._grid_to_mm(comp.center.y - 20)} 0) (effects (font (size 1.27 1.27))))',
            f'    (property "Value" "{val}" (at {x} {self._grid_to_mm(comp.center.y + 20)} 0) (effects (font (size 1.27 1.27))))'
        ]
        if source and source.footprint:
            lines.append(f'    (property "Footprint" "{source.footprint}" (at {x} {y} 0) (hide yes) (effects (font (size 1.27 1.27))))')
        lines.append("  )")
        return lines

    def _write_trace(self, trace: SchematicTrace) -> List[str]:
        lines = []
        for edge in trace.edges:
            x1, y1 = self._grid_to_mm(edge.from_.x), self._grid_to_mm(edge.from_.y)
            x2, y2 = self._grid_to_mm(edge.to.x), self._grid_to_mm(edge.to.y)
            lines.append(f'  (wire (pts (xy {x1} {y1}) (xy {x2} {y2})) (stroke (width 0) (type default)) (uuid "{self._new_uuid()}"))')
        return lines

    def _write_label(self, label: SchematicNetLabel) -> List[str]:
        x = self._grid_to_mm(label.center.x); y = self._grid_to_mm(label.center.y)
        angle = {"right": 0, "top": 90, "left": 180, "bottom": 270}.get(label.anchor_side, 0)
        justify = label.anchor_side
        return [f'  (label "{label.text}" (at {x} {y} {angle}) (effects (font (size 1.27 1.27)) (justify {justify})) (uuid "{self._new_uuid()}"))']

    def _write_text(self, text: SchematicText) -> List[str]:
        x = self._grid_to_mm(text.position.x); y = self._grid_to_mm(text.position.y)
        return [f'  (text "{text.text.replace("\n", "\\n")}" (at {x} {y} {text.rotation}) (effects (font (size 1.27 1.27)) (justify left)) (uuid "{self._new_uuid()}"))']

    def _write_box(self, box: SchematicBox) -> List[str]:
        x1, y1 = self._grid_to_mm(box.x), self._grid_to_mm(box.y)
        x2, y2 = self._grid_to_mm(box.x + box.width), self._grid_to_mm(box.y + box.height)
        return [f'  (rectangle (start {x1} {y1}) (end {x2} {y2}) (stroke (width 0.1524) (type default)) (fill (type none)) (uuid "{self._new_uuid()}"))']

    def write_project(self, project_name: str, sheet_ids: List[str]) -> str:
        sheets = [["Root", f"{project_name}.kicad_sch"]]
        for sid in sheet_ids:
            if sid != "root": sheets.append([sid, f"{sid}.kicad_sch"])
        import json
        return json.dumps({"meta": {"filename": f"{project_name}.kicad_pro", "version": 3}, "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []}, "boards": [], "sheets": sheets}, indent=2)

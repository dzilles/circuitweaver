"""KiCad schematic file writer with multi-sheet support."""

import logging
import re
import uuid
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from circuitweaver.library.pinout import get_expanded_symbol_definition, SymbolInfo
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


class SExp:
    """A lightweight S-Expression builder."""

    def __init__(self, name: str, *args: Any):
        self.name = name
        self.args = list(args)

    def serialize(self, indent_level: int = 0) -> str:
        """Serialize to string with proper indentation and quoting."""
        indent = "  " * indent_level
        inner = []
        for arg in self.args:
            if isinstance(arg, SExp):
                inner.append("\n" + arg.serialize(indent_level + 1))
            elif isinstance(arg, (list, tuple)):
                for item in arg:
                    if isinstance(item, SExp):
                        inner.append("\n" + item.serialize(indent_level + 1))
                    else:
                        inner.append(self._format_value(item))
            else:
                formatted = self._format_value(arg)
                if formatted:
                    inner.append(formatted)

        inner_str = " ".join(inner)
        return f"{indent}({self.name} {inner_str})"

    def _format_value(self, val: Any) -> str:
        if val is None:
            return ""
        if isinstance(val, bool):
            return "yes" if val else "no"
        if isinstance(val, (int, float, Decimal)):
            return str(val)
        
        s = str(val)
        if any(c in s for c in ' ()"\t\n') or not s:
            escaped = s.replace('"', '\\"')
            return f'"{escaped}"'
        return s


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

        sch = SExp("kicad_sch",
            SExp("version", 20260306),
            SExp("generator", "eeschema"),
            SExp("generator_version", "10.0"),
            SExp("uuid", self._new_uuid()),
            SExp("paper", "A4"),
        )

        sheet_components = [e for e in sheet_elements if isinstance(e, SchematicComponent)]
        sheet_pins = [e for e in sheet_elements if isinstance(e, SchematicHierarchicalPin)]
        sheet_h_labels = [e for e in sheet_elements if isinstance(e, SchematicHierarchicalLabel)]
        sheet_net_labels = [e for e in sheet_elements if isinstance(e, SchematicNetLabel)]
        
        # 1. Symbol Library definitions
        lib_symbols = SExp("lib_symbols")
        if sheet_components:
            symbols_needed, lib_id_to_lib_name = self._collect_symbols_recursive(
                sheet_components, source_components
            )
            for symbol_def in symbols_needed:
                # symbol_def is already a string, we inject it manually in serialize or handle it here
                # For simplicity, we can store it as a special type or just a string that SExp knows not to quote
                # But our _format_value quotes everything with spaces. 
                # Let's add a RawSExp or handle strings starting with '(' as raw for now.
                lib_symbols.args.append(symbol_def)
        else:
            lib_id_to_lib_name = {}
        sch.args.append(lib_symbols)

        # 2. Hierarchical Sheets (Boxes)
        sheet_boxes = [e for e in sheet_elements if isinstance(e, SchematicBox) and e.is_hierarchical_sheet]
        for box in sheet_boxes:
            pins = [p for p in sheet_pins if p.schematic_box_id == box.schematic_box_id]
            sch.args.append(self._write_hierarchical_sheet(box, pins))

        # 3. Component Instances
        for comp in sheet_components:
            source = source_components.get(comp.source_component_id)
            symbol = None
            if source and source.symbol_id:
                from circuitweaver.library.pinout import get_symbol_info
                try:
                    symbol = get_symbol_info(source.symbol_id)
                except Exception: pass
            sch.args.append(self._write_component(comp, source_components, lib_id_to_lib_name, symbol))

        # 4. Traces & Junctions
        point_counts = defaultdict(int)
        for element in sheet_elements:
            if isinstance(element, SchematicTrace):
                for wire in self._write_trace(element):
                    sch.args.append(wire)
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
                sch.args.append(SExp("junction", SExp("at", x_mm, y_mm), SExp("uuid", self._new_uuid())))

        # 5. Labels & Text & No-Connects
        for element in sheet_elements:
            if isinstance(element, SchematicNetLabel):
                sch.args.append(self._write_label(element))
            elif isinstance(element, SchematicHierarchicalLabel):
                sch.args.append(self._write_hierarchical_label(element))
            elif isinstance(element, SchematicText):
                sch.args.append(self._write_text(element))
            elif isinstance(element, SchematicNoConnect):
                nc = self._write_no_connect(element)
                if nc: sch.args.append(nc)

        # 6. Graphic Boxes
        for element in sheet_elements:
            if isinstance(element, SchematicBox) and not element.is_hierarchical_sheet:
                sch.args.append(self._write_box(element))

        sch.args.append(SExp("sheet_instances", SExp("path", "/", SExp("page", "1"))))
        sch.args.append(SExp("embedded_fonts", False))

        # We need to handle the raw symbol strings in serialize.
        # Let's override serialize slightly or adjust SExp.
        return self._serialize_sch(sch)

    def _serialize_sch(self, sch: SExp) -> str:
        # A simple hack: SExp._format_value normally quotes. 
        # We want to avoid quoting the symbol_def strings which start with whitespace and '('
        original_format = SExp._format_value
        def custom_format(self_obj, val):
            if isinstance(val, str) and val.strip().startswith("("):
                return val # Return as-is
            return original_format(self_obj, val)
        
        SExp._format_value = custom_format
        try:
            return sch.serialize()
        finally:
            SExp._format_value = original_format

    def _write_no_connect(self, nc: SchematicNoConnect) -> Optional[SExp]:
        if not nc.position: return None
        x = self._grid_to_mm(nc.position.x)
        y = self._grid_to_mm(nc.position.y)
        return SExp("no_connect", SExp("at", x, y), SExp("uuid", self._new_uuid()))

    def _write_hierarchical_sheet(self, box: SchematicBox, pins: List[SchematicHierarchicalPin]) -> SExp:
        x = self._grid_to_mm(box.x); y = self._grid_to_mm(box.y)
        w = self._grid_to_mm(box.width); h = self._grid_to_mm(box.height)
        sheet_name = box.name or box.schematic_box_id
        file_name = f"{box.schematic_box_id.replace('box_', '')}.kicad_sch"
        
        x_mid_mm = self._grid_to_mm(box.x + box.width / 2)
        ny_mm = self._grid_to_mm(box.y + box.name_offset.y)
        fy_mm = self._grid_to_mm(box.y + box.file_offset.y)
        
        inner_pins = []
        for pin in pins:
            px = self._grid_to_mm(pin.center.x)
            py = self._grid_to_mm(pin.center.y)
            justify = "left" if int(round(pin.center.x)) <= int(round(box.x)) else "right"
            angle = 180 if int(round(pin.center.x)) <= int(round(box.x)) else 0
            inner_pins.append(SExp("pin", pin.text, "input", 
                SExp("at", px, py, angle), 
                SExp("uuid", self._new_uuid()),
                SExp("effects", SExp("font", SExp("size", 1.27, 1.27)), SExp("justify", justify))
            ))

        return SExp("sheet", 
            SExp("at", x, y), SExp("size", w, h),
            SExp("fields_autoplaced", True),
            SExp("stroke", SExp("width", 0.1524), SExp("type", "solid")),
            SExp("fill", SExp("color", 0, 0, 0, 0)),
            SExp("uuid", self._new_uuid()),
            SExp("property", "Sheetname", sheet_name, SExp("at", x_mid_mm, ny_mm, 0), SExp("effects", SExp("font", SExp("size", 1.27, 1.27)), SExp("justify", "left", "top"))),
            SExp("property", "Sheetfile", file_name, SExp("at", x_mid_mm, fy_mm, 0), SExp("effects", SExp("font", SExp("size", 1.27, 1.27)), SExp("justify", "left", "top"))),
            *inner_pins
        )

    def _write_hierarchical_label(self, label: SchematicHierarchicalLabel) -> SExp:
        x = self._grid_to_mm(label.center.x); y = self._grid_to_mm(label.center.y)
        angle = {"right": 0, "top": 90, "left": 180, "bottom": 270}.get(label.anchor_side, 0)
        justify = label.anchor_side
        return SExp("hierarchical_label", label.text, SExp("shape", "input"),
            SExp("at", x, y, angle),
            SExp("effects", SExp("font", SExp("size", 1.27, 1.27)), SExp("justify", justify)),
            SExp("uuid", self._new_uuid())
        )

    def _write_label(self, label: SchematicNetLabel) -> SExp:
        x = self._grid_to_mm(label.center.x); y = self._grid_to_mm(label.center.y)
        angle = {"right": 0, "top": 90, "left": 180, "bottom": 270}.get(label.anchor_side, 0)
        justify = label.anchor_side
        return SExp("label", label.text, SExp("at", x, y, angle),
            SExp("effects", SExp("font", SExp("size", 1.27, 1.27)), SExp("justify", justify)),
            SExp("uuid", self._new_uuid())
        )

    def _write_text(self, text: SchematicText) -> SExp:
        x = self._grid_to_mm(text.position.x); y = self._grid_to_mm(text.position.y)
        return SExp("text", text.text.replace("\n", "\\n"), 
            SExp("at", x, y, text.rotation),
            SExp("effects", SExp("font", SExp("size", 1.27, 1.27)), SExp("justify", "left")),
            SExp("uuid", self._new_uuid())
        )

    def _write_box(self, box: SchematicBox) -> SExp:
        x1, y1 = self._grid_to_mm(box.x), self._grid_to_mm(box.y)
        x2, y2 = self._grid_to_mm(box.x + box.width), self._grid_to_mm(box.y + box.height)
        return SExp("rectangle", SExp("start", x1, y1), SExp("end", x2, y2),
            SExp("stroke", SExp("width", 0.1524), SExp("type", "default")),
            SExp("fill", SExp("type", "none")),
            SExp("uuid", self._new_uuid())
        )

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

    def _write_component(self, comp: SchematicComponent, sources: Dict[str, SourceComponent], lib_id_to_lib_name: Dict[str, str], symbol: Optional[SymbolInfo] = None) -> SExp:
        source = sources.get(comp.source_component_id)
        lib_id = self._resolve_lib_id(comp, source)
        lib_name = lib_id_to_lib_name.get(lib_id, lib_id)
        ref = source.name if source else "U?"
        val = source.display_value if source and source.display_value else (source.symbol_id if source else "")
        x = self._grid_to_mm(comp.center.x); y = self._grid_to_mm(comp.center.y)
        ref_y = self._grid_to_mm(comp.center.y - 20)
        val_y = self._grid_to_mm(comp.center.y + 20)
        
        sexp = SExp("symbol",
            SExp("lib_name", lib_name),
            SExp("lib_id", lib_id),
            SExp("at", x, y, comp.rotation),
            SExp("unit", 1),
            SExp("body_style", 1),
            SExp("exclude_from_sim", False),
            SExp("in_bom", True),
            SExp("on_board", True),
            SExp("in_pos_files", True),
            SExp("dnp", False),
            SExp("fields_autoplaced", True),
            SExp("uuid", self._new_uuid()),
            SExp("property", "Reference", ref, 
                SExp("at", x, ref_y, 0),
                SExp("effects", SExp("font", SExp("size", 1.27, 1.27)), SExp("justify", "left"))
            ),
            SExp("property", "Value", val,
                SExp("at", x, val_y, 0),
                SExp("effects", SExp("font", SExp("size", 1.27, 1.27)), SExp("justify", "left"))
            )
        )
        
        if source and source.footprint:
            sexp.args.append(SExp("property", "Footprint", source.footprint,
                SExp("at", x, y, 0),
                SExp("hide", True),
                SExp("effects", SExp("font", SExp("size", 1.27, 1.27)), SExp("justify", "right"))
            ))
        
        if symbol:
            for pin in symbol.pins:
                sexp.args.append(SExp("pin", pin.number, SExp("uuid", self._new_uuid())))
        
        return sexp

    def _write_trace(self, trace: SchematicTrace) -> List[SExp]:
        sexps = []
        for edge in trace.edges:
            x1, y1 = self._grid_to_mm(edge.from_.x), self._grid_to_mm(edge.from_.y)
            x2, y2 = self._grid_to_mm(edge.to.x), self._grid_to_mm(edge.to.y)
            sexps.append(SExp("wire", 
                SExp("pts", SExp("xy", x1, y1), SExp("xy", x2, y2)),
                SExp("stroke", SExp("width", 0), SExp("type", "default")),
                SExp("uuid", self._new_uuid())
            ))
        return sexps

    def write_project(self, project_name: str, sheet_ids: List[str]) -> str:
        sheets = [["Root", f"{project_name}.kicad_sch"]]
        for sid in sheet_ids:
            if sid != "root": sheets.append([sid, f"{sid}.kicad_sch"])
        import json
        return json.dumps({"meta": {"filename": f"{project_name}.kicad_pro", "version": 3}, "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []}, "boards": [], "sheets": sheets}, indent=2)

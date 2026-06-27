"""Transform Schematic elements to S-expression tree.

Transforms Schematic types (visual elements) into S-expression trees
that can be serialized to KiCad schematic files.
"""

import logging
import uuid
from collections import defaultdict
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from circuitweaver.transform.source_to_layout import get_effective_symbol_id
from circuitweaver.types import (
    CircuitElement,
    RawString,
    SchematicBox,
    SchematicComponent,
    SchematicHierarchicalLabel,
    SchematicHierarchicalPin,
    SchematicNetLabel,
    SchematicNoConnect,
    SchematicPort,
    SchematicText,
    SchematicTrace,
    SExpr,
    SourceComponent,
)

logger = logging.getLogger(__name__)

# Grid unit to mm conversion (1 grid = 5mil = 0.127mm)
GRID_TO_MM = Decimal("0.127")


class SchematicToSExprTransform:
    """Transforms Schematic elements into KiCad S-expression trees.

    The resulting SExpr can be serialized to a .kicad_sch file.
    """

    def __init__(self, uuid_factory: Callable[[], str] | None = None):
        self.uuid_factory = uuid_factory

    def _new_uuid(self) -> str:
        """Generate a new UUID for KiCad elements."""
        if self.uuid_factory is not None:
            return self.uuid_factory()
        return str(uuid.uuid4())

    def _grid_to_mm(self, grid: float) -> str:
        """Convert grid units to millimeters, preserving fractional precision."""
        val = Decimal(str(grid)) * GRID_TO_MM
        return f"{val:.4f}"

    def transform(
        self,
        elements: list[CircuitElement],
        sheet_id: str,
        source_components: dict[str, SourceComponent],
    ) -> SExpr:
        """Transform Schematic elements into a KiCad schematic S-expression.

        Args:
            elements: All circuit elements.
            sheet_id: ID of the sheet to transform.
            source_components: Mapping of source component IDs to SourceComponent.

        Returns:
            SExpr tree representing the KiCad schematic.
        """
        sheet_elements = [
            e for e in elements
            if not hasattr(e, "sheet_id") or e.sheet_id == sheet_id
        ]

        sch = SExpr(
            "kicad_sch",
            SExpr("version", 20260306),
            SExpr("generator", "eeschema"),
            SExpr("generator_version", "10.0"),
            SExpr("uuid", self._new_uuid()),
            SExpr("paper", "A4"),
        )

        sheet_components = [e for e in sheet_elements if isinstance(e, SchematicComponent)]
        sheet_hier_pins = [e for e in sheet_elements if isinstance(e, SchematicHierarchicalPin)]
        sheet_ports = [e for e in sheet_elements if isinstance(e, SchematicPort)]
        sheet_h_labels = [e for e in sheet_elements if isinstance(e, SchematicHierarchicalLabel)]
        sheet_net_labels = [e for e in sheet_elements if isinstance(e, SchematicNetLabel)]

        # 1. Symbol Library definitions
        lib_symbols = SExpr("lib_symbols")
        if sheet_components:
            symbols_needed, lib_id_to_lib_name = self._collect_symbols_recursive(
                sheet_components, source_components
            )
            for symbol_def in symbols_needed:
                lib_symbols.args.append(RawString(symbol_def))
        else:
            lib_id_to_lib_name = {}
        sch.args.append(lib_symbols)

        # 2. Hierarchical Sheets (Boxes)
        sheet_boxes = [e for e in sheet_elements if isinstance(e, SchematicBox) and e.is_hierarchical_sheet]
        for box in sheet_boxes:
            pins = [p for p in sheet_hier_pins if p.schematic_box_id == box.schematic_box_id]
            sch.args.append(self._transform_hierarchical_sheet(box, pins))

        # 3. Component Instances
        for comp in sheet_components:
            source = source_components.get(comp.source_component_id)
            symbol = None
            symbol_id = get_effective_symbol_id(source) if source else None
            if symbol_id:
                from circuitweaver.library.pinout import get_symbol_info
                try:
                    symbol = get_symbol_info(symbol_id)
                except Exception as e:
                    logger.warning(f"Could not load symbol info for {symbol_id}: {e}")
            sch.args.append(self._transform_component(comp, source_components, lib_id_to_lib_name, symbol))

        # 4. Traces & Junctions
        point_counts = defaultdict(int)
        for element in sheet_elements:
            if isinstance(element, SchematicTrace):
                for wire in self._transform_trace(element):
                    sch.args.append(wire)
                for edge in element.edges:
                    point_counts[(int(round(edge.from_.x)), int(round(edge.from_.y)))] += 1
                    point_counts[(int(round(edge.to.x)), int(round(edge.to.y)))] += 1

        for pin in sheet_hier_pins:
            point_counts[(int(round(pin.center.x)), int(round(pin.center.y)))] += 1
        for port in sheet_ports:
            point_counts[(int(round(port.center.x)), int(round(port.center.y)))] += 1
        for lbl in sheet_h_labels:
            point_counts[(int(round(lbl.center.x)), int(round(lbl.center.y)))] += 1
        for lbl in sheet_net_labels:
            point_counts[(int(round(lbl.center.x)), int(round(lbl.center.y)))] += 1

        for (gx, gy), count in point_counts.items():
            if count >= 3:
                x_mm = self._grid_to_mm(gx)
                y_mm = self._grid_to_mm(gy)
                sch.args.append(SExpr("junction", SExpr("at", x_mm, y_mm), SExpr("uuid", self._new_uuid())))

        # 5. Labels & Text & No-Connects
        for element in sheet_elements:
            if isinstance(element, SchematicNetLabel):
                sch.args.append(self._transform_label(element))
            elif isinstance(element, SchematicHierarchicalLabel):
                sch.args.append(self._transform_hierarchical_label(element))
            elif isinstance(element, SchematicText):
                sch.args.append(self._transform_text(element))
            elif isinstance(element, SchematicNoConnect):
                nc = self._transform_no_connect(element)
                if nc:
                    sch.args.append(nc)

        # 6. Graphic Boxes
        for element in sheet_elements:
            if isinstance(element, SchematicBox) and not element.is_hierarchical_sheet:
                sch.args.append(self._transform_box(element))

        sch.args.append(SExpr("sheet_instances", SExpr("path", "/", SExpr("page", "1"))))
        sch.args.append(SExpr("embedded_fonts", False))

        return sch

    def _transform_no_connect(self, nc: SchematicNoConnect) -> SExpr | None:
        if not nc.position:
            return None
        x = self._grid_to_mm(nc.position.x)
        y = self._grid_to_mm(nc.position.y)
        return SExpr("no_connect", SExpr("at", x, y), SExpr("uuid", self._new_uuid()))

    def _transform_hierarchical_sheet(self, box: SchematicBox, pins: list[SchematicHierarchicalPin]) -> SExpr:
        x = self._grid_to_mm(box.x)
        y = self._grid_to_mm(box.y)
        w = self._grid_to_mm(box.width)
        h = self._grid_to_mm(box.height)
        sheet_name = box.name or box.schematic_box_id
        file_name = f"{box.child_sheet_id}.kicad_sch" if box.child_sheet_id else f"{box.schematic_box_id.replace('box_', '')}.kicad_sch"

        x_mid_mm = self._grid_to_mm(box.x + box.width / 2)
        ny_mm = self._grid_to_mm(box.y + box.name_offset.y)
        fy_mm = self._grid_to_mm(box.y + box.file_offset.y)

        inner_pins = []
        for pin in pins:
            px = self._grid_to_mm(pin.center.x)
            py = self._grid_to_mm(pin.center.y)
            justify = "left" if int(round(pin.center.x)) <= int(round(box.x)) else "right"
            angle = 180 if int(round(pin.center.x)) <= int(round(box.x)) else 0
            inner_pins.append(SExpr(
                "pin", pin.text, "input",
                SExpr("at", px, py, angle),
                SExpr("uuid", self._new_uuid()),
                SExpr("effects", SExpr("font", SExpr("size", 1.27, 1.27)), SExpr("justify", justify))
            ))

        return SExpr(
            "sheet",
            SExpr("at", x, y), SExpr("size", w, h),
            SExpr("fields_autoplaced", True),
            SExpr("stroke", SExpr("width", 0.1524), SExpr("type", "solid")),
            SExpr("fill", SExpr("color", 0, 0, 0, 0)),
            SExpr("uuid", self._new_uuid()),
            SExpr("property", "Sheetname", sheet_name, SExpr("at", x_mid_mm, ny_mm, 0),
                  SExpr("effects", SExpr("font", SExpr("size", 1.27, 1.27)), SExpr("justify", "left", "top"))),
            SExpr("property", "Sheetfile", file_name, SExpr("at", x_mid_mm, fy_mm, 0),
                  SExpr("effects", SExpr("font", SExpr("size", 1.27, 1.27)), SExpr("justify", "left", "top"))),
            *inner_pins
        )

    def _transform_hierarchical_label(self, label: SchematicHierarchicalLabel) -> SExpr:
        x = self._grid_to_mm(label.center.x)
        y = self._grid_to_mm(label.center.y)
        angle = {"right": 0, "top": 90, "left": 180, "bottom": 270}.get(label.anchor_side, 0)
        justify = label.anchor_side
        return SExpr(
            "hierarchical_label", label.text, SExpr("shape", "input"),
            SExpr("at", x, y, angle),
            SExpr("effects", SExpr("font", SExpr("size", 1.27, 1.27)), SExpr("justify", justify)),
            SExpr("uuid", self._new_uuid())
        )

    def _transform_label(self, label: SchematicNetLabel) -> SExpr:
        x = self._grid_to_mm(label.center.x)
        y = self._grid_to_mm(label.center.y)
        angle = {"right": 0, "top": 90, "left": 180, "bottom": 270}.get(label.anchor_side, 0)
        justify = label.anchor_side
        if label.is_global:
            return SExpr(
                "global_label", label.text, SExpr("shape", "input"),
                SExpr("at", x, y, angle),
                SExpr("effects", SExpr("font", SExpr("size", 1.27, 1.27)), SExpr("justify", justify)),
                SExpr("uuid", self._new_uuid())
            )
        return SExpr(
            "label", label.text, SExpr("at", x, y, angle),
            SExpr("effects", SExpr("font", SExpr("size", 1.27, 1.27)), SExpr("justify", justify)),
            SExpr("uuid", self._new_uuid())
        )

    def _transform_text(self, text: SchematicText) -> SExpr:
        x = self._grid_to_mm(text.position.x)
        y = self._grid_to_mm(text.position.y)
        return SExpr(
            "text", text.text.replace("\n", "\\n"),
            SExpr("at", x, y, text.rotation),
            SExpr("effects", SExpr("font", SExpr("size", 1.27, 1.27)), SExpr("justify", "left")),
            SExpr("uuid", self._new_uuid())
        )

    def _transform_box(self, box: SchematicBox) -> SExpr:
        x1, y1 = self._grid_to_mm(box.x), self._grid_to_mm(box.y)
        x2, y2 = self._grid_to_mm(box.x + box.width), self._grid_to_mm(box.y + box.height)
        return SExpr(
            "rectangle", SExpr("start", x1, y1), SExpr("end", x2, y2),
            SExpr("stroke", SExpr("width", 0.1524), SExpr("type", "default")),
            SExpr("fill", SExpr("type", "none")),
            SExpr("uuid", self._new_uuid())
        )

    def _resolve_lib_id(self, comp: SchematicComponent, source: SourceComponent | None) -> str:
        if comp.symbol_name and ":" in comp.symbol_name:
            return comp.symbol_name
        if source and (symbol_id := get_effective_symbol_id(source)):
            return symbol_id
        return "Device:QuestionBlock"

    def _collect_symbols_recursive(
        self,
        components: list[SchematicComponent],
        sources: dict[str, SourceComponent],
    ) -> tuple[list[str], dict[str, str]]:
        embedded_defs = {}
        lib_id_to_lib_name = {}
        processed = set()
        counter = 0

        for comp in components:
            source = sources.get(comp.source_component_id)
            lib_id = self._resolve_lib_id(comp, source)
            if lib_id.startswith("ERROR:") or lib_id.startswith("hierarchy:") or lib_id in processed:
                continue
            processed.add(lib_id)
            lib_parts = lib_id.split(":", 1)
            if len(lib_parts) < 2:
                continue
            lib_name, sym_name = lib_parts

            counter += 1
            embedded_name = f"Sym_{counter}"
            lib_id_to_lib_name[lib_id] = embedded_name
            try:
                from circuitweaver.library.pinout import get_expanded_symbol_definition
                symbol_def = get_expanded_symbol_definition(sym_name, library_name=lib_name, rename_to=embedded_name)
                embedded_defs[embedded_name] = self._indent_sexp(symbol_def, indent=4)
            except Exception as e:
                logger.warning(f"Could not embed {lib_id}: {e}")

        return ([embedded_defs[k] for k in sorted(embedded_defs.keys())], lib_id_to_lib_name)

    def _indent_sexp(self, sexp: str, indent: int = 4) -> str:
        prefix = " " * indent
        return "\n".join(prefix + line if line.strip() else line for line in sexp.split("\n"))

    def _transform_component(
        self,
        comp: SchematicComponent,
        sources: dict[str, SourceComponent],
        lib_id_to_lib_name: dict[str, str],
        symbol: Any | None = None,
    ) -> SExpr:
        source = sources.get(comp.source_component_id)
        lib_id_orig = self._resolve_lib_id(comp, source)
        lib_id = lib_id_to_lib_name.get(lib_id_orig, lib_id_orig)

        ref = source.name if source else "U?"
        symbol_id = get_effective_symbol_id(source) if source else None
        val = source.display_value if source and source.display_value else (symbol_id if source else "")
        x = self._grid_to_mm(comp.center.x)
        y = self._grid_to_mm(comp.center.y)
        ref_y = self._grid_to_mm(comp.center.y - 20)
        val_y = self._grid_to_mm(comp.center.y + 20)

        sexp = SExpr(
            "symbol",
            SExpr("lib_id", lib_id),
            SExpr("at", x, y, comp.rotation),
            SExpr("unit", 1),
            SExpr("body_style", 1),
            SExpr("exclude_from_sim", False),
            SExpr("in_bom", True),
            SExpr("on_board", True),
            SExpr("in_pos_files", True),
            SExpr("dnp", False),
            SExpr("fields_autoplaced", True),
            SExpr("uuid", self._new_uuid()),
            SExpr("property", "Reference", ref,
                  SExpr("at", x, ref_y, 0),
                  SExpr("show_name", False),
                  SExpr("do_not_autoplace", False),
                  SExpr("effects", SExpr("font", SExpr("size", 1.27, 1.27)), SExpr("justify", "left"))),
            SExpr("property", "Value", val,
                  SExpr("at", x, val_y, 0),
                  SExpr("show_name", False),
                  SExpr("do_not_autoplace", False),
                  SExpr("effects", SExpr("font", SExpr("size", 1.27, 1.27)), SExpr("justify", "left")))
        )

        if source and source.footprint:
            sexp.args.append(SExpr(
                "property", "Footprint", source.footprint,
                SExpr("at", x, y, 0),
                SExpr("hide", True),
                SExpr("effects", SExpr("font", SExpr("size", 1.27, 1.27)), SExpr("justify", "right"))
            ))

        if symbol:
            for pin in symbol.pins:
                sexp.args.append(SExpr("pin", pin.number, SExpr("uuid", self._new_uuid())))

        return sexp

    def _transform_trace(self, trace: SchematicTrace) -> list[SExpr]:
        sexps = []
        for edge in trace.edges:
            x1, y1 = self._grid_to_mm(edge.from_.x), self._grid_to_mm(edge.from_.y)
            x2, y2 = self._grid_to_mm(edge.to.x), self._grid_to_mm(edge.to.y)
            sexps.append(SExpr(
                "wire",
                SExpr("pts", SExpr("xy", x1, y1), SExpr("xy", x2, y2)),
                SExpr("stroke", SExpr("width", 0), SExpr("type", "default")),
                SExpr("uuid", self._new_uuid())
            ))
        return sexps

    def transform_project(self, project_name: str, sheet_ids: list[str]) -> str:
        """Transform project metadata to KiCad project JSON.

        Args:
            project_name: Name of the project.
            sheet_ids: List of all sheet IDs.

        Returns:
            JSON string for .kicad_pro file.
        """
        import json

        sheets = [["Root", f"{project_name}.kicad_sch"]]
        for sid in sheet_ids:
            if sid != "root":
                sheets.append([sid, f"{sid}.kicad_sch"])

        return json.dumps({
            "meta": {"filename": f"{project_name}.kicad_pro", "version": 3},
            "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
            "boards": [],
            "sheets": sheets,
        }, indent=2)

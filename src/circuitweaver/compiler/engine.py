"""Main compilation engine for CircuitWeaver.

Orchestrates the full pipeline from Source elements to KiCad files:
1. Source → Layout (ELK graph)
2. Layout → Layout (auto-routing via ELK)
3. Layout → Schematic (positioned elements)
4. Schematic → S-expression (KiCad format)
5. S-expression → .kicad_sch files
"""

import json
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from circuitweaver.library.pinout import get_symbol_info
from circuitweaver.types import (
    CircuitElement,
    LayoutNode,
    Point,
    SchematicHierarchicalLabel,
    SchematicHierarchicalPin,
    SchematicNetLabel,
    SourceComponent,
    SourceGroup,
    SourceNet,
    SourcePort,
    SourceTrace,
    get_element_id,
    s_expr_serialize,
)
from circuitweaver.transform import (
    SourceToLayoutTransform,
    LayoutToSchematicTransform,
    SchematicToSExprTransform,
    get_effective_symbol_id,
)
from circuitweaver.compiler.auto_router import AutoRouter

logger = logging.getLogger(__name__)

DEBUG_ELK = os.environ.get("CIRCUITWEAVER_DEBUG_ELK", "").lower() in ("1", "true", "yes")


class CompileEngine:
    """Main engine for compiling Circuit JSON to KiCad schematics.

    Orchestrates the full transformation pipeline and file output.
    """

    def __init__(self, helper_path: Optional[str] = None, kicad_cli_path: str = "kicad-cli"):
        """Initialize the compile engine.

        Args:
            helper_path: Path to the ELK layout helper JS file.
            kicad_cli_path: Path to kicad-cli for ERC checks.
        """
        self.router = AutoRouter(helper_path=Path(helper_path) if helper_path else None)
        self.kicad_cli_path = kicad_cli_path

    def compile(
        self,
        elements: List[CircuitElement],
        output_dir: Path,
        project_name: str = "project",
    ) -> Path:
        """Compile Circuit JSON to KiCad schematic files.

        1. Run auto-layout to generate schematic_* elements if missing.
        2. Transform to S-expressions.
        3. Write .kicad_sch and .kicad_pro files.

        Args:
            elements: List of circuit elements.
            output_dir: Directory to write output files.
            project_name: Name for the KiCad project.

        Returns:
            Path to the root schematic file.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        # Run layout if needed
        has_layout = any(e.type.startswith("schematic_") for e in elements)
        if not has_layout:
            logger.info("No layout found, running auto-layout...")
            elements = self.layout(elements)
        else:
            logger.info("Layout found in input, skipping auto-layout.")

        # Identify all sheets
        all_sheet_ids: Set[str] = set()
        for e in elements:
            if hasattr(e, "sheet_id"):
                all_sheet_ids.add(e.sheet_id)
        if not all_sheet_ids:
            all_sheet_ids.add("root")

        # Prepare source components map
        source_components: Dict[str, SourceComponent] = {
            e.source_component_id: e for e in elements if isinstance(e, SourceComponent)
        }

        # Transform and write each sheet
        transform = SchematicToSExprTransform()
        root_sch_file = None

        for sheet_id in all_sheet_ids:
            sexp = transform.transform(elements, sheet_id, source_components)
            content = s_expr_serialize(sexp)

            if sheet_id == "root":
                filename = f"{project_name}.kicad_sch"
                root_sch_file = output_dir / filename
            else:
                filename = f"{sheet_id}.kicad_sch"

            (output_dir / filename).write_text(content)
            logger.info(f"Wrote sheet '{sheet_id}' to {output_dir / filename}")

        # Write project file
        pro_content = transform.transform_project(project_name, list(all_sheet_ids))
        pro_file = output_dir / f"{project_name}.kicad_pro"
        pro_file.write_text(pro_content)
        logger.info(f"Wrote project to {pro_file}")

        return root_sch_file

    def layout(
        self,
        elements: List[CircuitElement],
        debug_dir: Optional[Path] = None,
        debug_basename: Optional[str] = None,
    ) -> List[CircuitElement]:
        """Run auto-layout on source elements.

        Transforms Source elements into positioned Schematic elements.

        Args:
            elements: List of circuit elements.
            debug_dir: Optional directory to write ELK debug files.
            debug_basename: Optional base filename for ELK debug files.

        Returns:
            Elements with added Schematic elements.
        """
        source_components = [e for e in elements if isinstance(e, SourceComponent)]
        source_groups = [e for e in elements if isinstance(e, SourceGroup)]
        source_ports = [e for e in elements if isinstance(e, SourcePort)]
        source_traces = [e for e in elements if isinstance(e, SourceTrace)]
        source_nets = [e for e in elements if isinstance(e, SourceNet)]

        if not source_components:
            return elements

        # 1. Map elements to sheets and load symbols
        element_to_sheet, element_to_group = self._map_elements(
            source_components, source_groups, source_ports
        )
        
        # Use subcircuit_id for sheet IDs, matching _map_elements
        subcircuit_ids = {g.subcircuit_id for g in source_groups if g.is_subcircuit and g.subcircuit_id}
        all_sheet_ids = {"root"} | subcircuit_ids
        symbol_map = self._load_symbols(source_components)

        # 2. Connectivity pre-processing
        connectivity_elements, sheet_connectivity = self._process_connectivity(
            source_traces, source_ports, source_nets,
            element_to_sheet, element_to_group, source_groups, elements
        )

        final_positioned_elements: List[CircuitElement] = []

        # 3. Process each sheet
        for sheet_id in all_sheet_ids:
            sheet_elements = self._get_sheet_elements(
                elements + connectivity_elements,
                element_to_sheet,
                sheet_id,
            )
            sheet_boxes = [
                g for g in source_groups
                if g.is_subcircuit and element_to_sheet.get(g.source_group_id) == sheet_id
            ]

            if not sheet_elements and not sheet_boxes:
                continue

            all_sheet_elements = sheet_elements + sheet_boxes

            # Transform: Source → Layout
            source_to_layout = SourceToLayoutTransform(symbol_map=symbol_map)
            layout_node, registry = source_to_layout.transform(
                sheet_id=sheet_id,
                elements=all_sheet_elements,
                sheet_connectivity=sheet_connectivity,
            )

            # Run ELK auto-router
            elk_dict = layout_node.model_dump()
            if DEBUG_ELK or (debug_dir and debug_basename):
                if debug_dir and debug_basename:
                    suffix = "" if sheet_id == "root" else f"_{sheet_id}"
                    debug_dir.joinpath(f"{debug_basename}_layout_in{suffix}.json").write_text(json.dumps(elk_dict, indent=2))
                else:
                    Path(f"debug_elk_in_{sheet_id}.json").write_text(json.dumps(elk_dict, indent=2))

            layout_results_dict = self.router.run(elk_dict)

            if DEBUG_ELK or (debug_dir and debug_basename):
                if debug_dir and debug_basename:
                    suffix = "" if sheet_id == "root" else f"_{sheet_id}"
                    debug_dir.joinpath(f"{debug_basename}_layout_out{suffix}.json").write_text(json.dumps(layout_results_dict, indent=2))
                else:
                    Path(f"debug_elk_out_{sheet_id}.json").write_text(json.dumps(layout_results_dict, indent=2))

            layout_results = LayoutNode.model_validate(layout_results_dict)

            # Transform: Layout → Schematic
            layout_to_schematic = LayoutToSchematicTransform(symbol_map=symbol_map)
            positioned_elements = layout_to_schematic.transform(
                sheet_id=sheet_id,
                layout_result=layout_results,
                registry=registry,
                elements=all_sheet_elements,
            )
            final_positioned_elements.extend(positioned_elements)

        # Filter to schematic elements only
        schematic_results = [
            e for e in final_positioned_elements
            if e.type.startswith("schematic_")
        ]

        return elements + connectivity_elements + schematic_results

    def _get_sheet_elements(
        self,
        elements: List[CircuitElement],
        element_to_sheet: Dict[str, str],
        sheet_id: str,
    ) -> List[CircuitElement]:
        """Get elements belonging to a specific sheet."""
        result = []
        for e in elements:
            if isinstance(e, (SourceTrace, SourceNet)):
                continue

            if hasattr(e, "sheet_id"):
                if e.sheet_id == sheet_id:
                    result.append(e)
            else:
                eid = get_element_id(e)
                if element_to_sheet.get(eid) == sheet_id:
                    result.append(e)

        return result

    def _map_elements(
        self,
        components: List[SourceComponent],
        groups: List[SourceGroup],
        ports: List[SourcePort],
    ) -> tuple[Dict[str, str], Dict[str, str]]:
        """Map elements to their sheets and groups."""
        element_to_sheet = {}
        element_to_group = {}
        group_map = {g.source_group_id: g for g in groups}

        def get_owner_sheet(gid: Optional[str]) -> str:
            """Recursively find the subcircuit_id that owns this group."""
            if not gid or gid not in group_map:
                return "root"
            g = group_map[gid]
            if g.is_subcircuit and g.subcircuit_id:
                return g.subcircuit_id
            return get_owner_sheet(g.parent_source_group_id)

        for c in components:
            pid = c.source_group_id or c.subcircuit_id
            # Resolve subcircuit_id to source_group_id if needed
            if pid and pid not in group_map:
                match = next((g for g in groups if g.subcircuit_id == pid), None)
                if match:
                    pid = match.source_group_id

            sheet = get_owner_sheet(pid)
            element_to_sheet[c.source_component_id] = sheet
            element_to_group[c.source_component_id] = pid or sheet

            for p in ports:
                if p.source_component_id == c.source_component_id:
                    element_to_sheet[p.source_port_id] = sheet

        for g in groups:
            # A group's owner sheet is determined by its parent
            sheet = get_owner_sheet(g.parent_source_group_id)
            element_to_sheet[g.source_group_id] = sheet
            element_to_group[g.source_group_id] = g.parent_source_group_id or sheet

        return element_to_sheet, element_to_group

    def _load_symbols(self, components: List[SourceComponent]) -> Dict[str, Any]:
        """Load symbol info for all components."""
        unique_symbols = {}
        for comp in components:
            symbol_id = get_effective_symbol_id(comp)
            if symbol_id and symbol_id not in unique_symbols:
                try:
                    unique_symbols[symbol_id] = get_symbol_info(symbol_id)
                except Exception as e:
                    logger.warning(f"Could not load symbol {symbol_id}: {e}")
        return unique_symbols

    def _process_connectivity(
        self,
        traces: List[SourceTrace],
        ports: List[SourcePort],
        nets: List[SourceNet],
        element_to_sheet: Dict[str, str],
        element_to_group: Dict[str, str],
        groups: List[SourceGroup],
        elements: List[CircuitElement],
    ) -> tuple[List[CircuitElement], Dict[str, List[Dict[str, Any]]]]:
        """Process connectivity to create labels and hierarchical pins."""
        generated = []
        sheet_connectivity = defaultdict(list)
        port_map = {p.source_port_id: p for p in ports}
        net_map = {n.source_net_id: n for n in nets}

        nets_to_ports = defaultdict(list)
        for trace in traces:
            involved_ports = [port_map[pid] for pid in trace.connected_source_port_ids if pid in port_map]
            if not involved_ports:
                continue

            net_id = trace.connected_source_net_ids[0] if trace.connected_source_net_ids else trace.source_trace_id
            raw_name = net_map[net_id].name if (trace.connected_source_net_ids and net_id in net_map) else trace.source_trace_id
            net_name, hier_name = f"NET_{raw_name}", f"HPIN_{raw_name}"
            nets_to_ports[(net_id, net_name, hier_name)].extend(involved_ports)

            involved_sheets = {element_to_sheet[p.source_port_id] for p in involved_ports if p.source_port_id in element_to_sheet}
            for sid in involved_sheets:
                ports_in_sheet = [p for p in involved_ports if element_to_sheet.get(p.source_port_id) == sid]
                sheet_connectivity[sid].append({
                    "trace_id": trace.source_trace_id,
                    "net_id": net_id,
                    "ports": [p.source_port_id for p in ports_in_sheet],
                    "is_inter_group": False,
                    "is_inter_sheet": False,
                    "hpin_id": None,
                })

        for (net_id, net_name, hier_name), involved_ports in nets_to_ports.items():
            involved_sheets = {element_to_sheet[p.source_port_id] for p in involved_ports if p.source_port_id in element_to_sheet}
            is_global = any(global_name in net_name.upper() for global_name in ["GND", "5V", "3V3"])
            sheet_to_hpin_id = {}
            is_inter_sheet = len(involved_sheets) > 1 and not is_global

            if is_inter_sheet:
                for sid in involved_sheets:
                    if sid == "root":
                        continue
                    curr = sid
                    while curr != "root":
                        parent = element_to_sheet.get(curr, "root")
                        hpin_id = f"hpin_{net_id}_{curr}"
                        if not any(
                            isinstance(e, SchematicHierarchicalPin) and e.schematic_hierarchical_pin_id == hpin_id
                            for e in elements + generated
                        ):
                            generated.append(SchematicHierarchicalPin(
                                schematic_hierarchical_pin_id=hpin_id,
                                sheet_id=parent,
                                source_net_id=net_id,
                                schematic_box_id=f"box_{curr}",
                                center=Point(x=0, y=0),
                                text=hier_name,
                            ))
                            ports_in_curr = [p for p in involved_ports if element_to_sheet.get(p.source_port_id) == curr]
                            if ports_in_curr:
                                hlabel_id = f"hlabel_{net_id}_{curr}"
                                generated.append(SchematicHierarchicalLabel(
                                    schematic_hierarchical_label_id=hlabel_id,
                                    sheet_id=curr,
                                    source_net_id=net_id,
                                    source_port_id=ports_in_curr[0].source_port_id,
                                    center=Point(x=0, y=0),
                                    text=hier_name,
                                ))
                        sheet_to_hpin_id[curr] = hpin_id
                        sheet_to_hpin_id[parent] = hpin_id
                        curr = parent

            for sid in involved_sheets:
                ports_in_sheet = [p for p in involved_ports if element_to_sheet.get(p.source_port_id) == sid]
                involved_groups = {element_to_group.get(p.source_component_id, "root") for p in ports_in_sheet}
                is_inter_group_on_sheet = len(involved_groups) > 1
                needs_local_labels = is_inter_group_on_sheet or is_global

                for conn in sheet_connectivity[sid]:
                    if conn["net_id"] == net_id:
                        conn["is_inter_group"] = is_inter_group_on_sheet
                        conn["is_inter_sheet"] = len(involved_sheets) > 1
                        conn["hpin_id"] = sheet_to_hpin_id.get(sid)

                if needs_local_labels:
                    for p in ports_in_sheet:
                        lbl_id = f"nlabel_{net_id}_{p.source_port_id}"
                        if not any(get_element_id(e) == lbl_id for e in generated):
                            generated.append(SchematicNetLabel(
                                schematic_net_label_id=lbl_id,
                                sheet_id=sid,
                                source_net_id=net_id,
                                source_port_id=p.source_port_id,
                                center=Point(x=0, y=0),
                                text=net_name,
                            ))

        return generated, sheet_connectivity

    def run_erc(self, schematic_path: Path) -> Dict[str, Any]:
        """Run ERC on a generated schematic.

        Args:
            schematic_path: Path to the .kicad_sch file.

        Returns:
            Dict with 'is_valid', 'errors', 'warnings'.
        """
        from circuitweaver.erc.checker import ERCChecker
        checker = ERCChecker(kicad_cli_path=self.kicad_cli_path)
        return checker.run(schematic_path)

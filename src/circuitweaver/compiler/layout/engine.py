import json
import logging
from collections import defaultdict
from pathlib import Path
import os
from typing import Any, Dict, List, Optional, Tuple

from circuitweaver.library.pinout import get_symbol_info, SymbolInfo
from circuitweaver.types.circuit_json import (
    CircuitElement,
    Point,
    SchematicHierarchicalLabel,
    SchematicNetLabel,
    SchematicNoConnect,
    SourceComponent,
    SourceGroup,
    SourceNet,
    SourcePort,
    SourceTrace,
    SchematicHierarchicalPin,
    get_element_id,
)
from ..elk_runner import ElkRunner
from .builder import ElkGraphBuilder
from .parser import ElkGraphParser

logger = logging.getLogger(__name__)

# Enable debug output via environment variable
DEBUG_ELK = os.environ.get("CIRCUITWEAVER_DEBUG_ELK", "").lower() in ("1", "true", "yes")


class AutoLayoutEngine:
    """
    Orchestrates hierarchical multi-sheet schematic layout using ELK.
    """

    def __init__(self, helper_path: Optional[str] = None):
        hpath = Path(helper_path) if helper_path else None
        self.runner = ElkRunner(helper_path=hpath)
        self.builder = ElkGraphBuilder()
        self.parser = ElkGraphParser()

    def layout(self, elements: List[CircuitElement]) -> List[CircuitElement]:
        """
        Main entry point to perform layout on a set of circuit elements.
        """
        source_components = [e for e in elements if isinstance(e, SourceComponent)]
        source_ports = [e for e in elements if isinstance(e, SourcePort)]
        source_traces = [e for e in elements if isinstance(e, SourceTrace)]
        source_groups = [e for e in elements if isinstance(e, SourceGroup)]
        source_nets = [e for e in elements if isinstance(e, SourceNet)]

        if not source_components:
            return elements

        # 1. Map elements to sheets
        element_to_sheet, element_to_group = self._map_elements(source_components, source_groups)
        subcircuit_group_ids = {g.source_group_id for g in source_groups if g.is_subcircuit}
        all_sheet_ids = {"root"} | subcircuit_group_ids

        # 2. Prepare Symbol Mapping
        unique_symbols = self._load_symbols(source_components)

        # 3. Analyze Connectivity and Generate Labels/Pins
        connectivity_elements, sheet_connectivity = self._process_connectivity(
            source_traces, source_ports, source_nets, element_to_sheet, element_to_group, source_groups, elements
        )

        final_positioned_elements: List[CircuitElement] = []
        ports_by_comp = defaultdict(list)
        for p in source_ports:
            ports_by_comp[p.source_component_id].append(p)

        # 4. Correct sheet_id for SchematicNoConnect flags
        # NC flags must be on the same sheet as the component they are attached to.
        port_to_sheet = {p.source_port_id: element_to_sheet.get(p.source_component_id, "root") for p in source_ports}
        for e in elements:
            if isinstance(e, SchematicNoConnect) and e.schematic_port_id:
                # Remove "port_" prefix if present
                pid = e.schematic_port_id.replace("port_", "")
                if pid in port_to_sheet:
                    e.sheet_id = port_to_sheet[pid]

        # 5. Sheet-by-Sheet Layout
        schematic_elements = [e for e in elements if isinstance(e, (SchematicNoConnect, SchematicNetLabel, SchematicHierarchicalLabel, SchematicHierarchicalPin))]
        for sheet_id in all_sheet_ids:
            sheet_results = self._layout_single_sheet(
                sheet_id, source_components, source_groups, element_to_sheet,
                ports_by_comp, sheet_connectivity, connectivity_elements + schematic_elements, unique_symbols
            )
            final_positioned_elements.extend(sheet_results)

        return elements + final_positioned_elements + connectivity_elements

    def _load_symbols(self, components: List[SourceComponent]) -> Dict[str, SymbolInfo]:
        """Load symbol information for all components.

        Also populates symbol_id on components that have ftype but no symbol_id.
        Note: This intentionally mutates components to set default symbol mappings.
        """
        FTYPE_MAP = {
            "simple_resistor": "Device:R",
            "simple_capacitor": "Device:C",
            "simple_led": "Device:LED",
            "simple_diode": "Device:D",
            "simple_transistor": "Device:Q_NPN_BCE",
        }

        unique_symbols: Dict[str, SymbolInfo] = {}
        for comp in components:
            # Apply default symbol mapping for known ftypes
            if not comp.symbol_id and comp.ftype in FTYPE_MAP:
                # Note: Intentionally mutating to persist the default symbol_id
                comp.symbol_id = FTYPE_MAP[comp.ftype]
                logger.debug(f"Applied default symbol {comp.symbol_id} for {comp.name} (ftype={comp.ftype})")

            if comp.symbol_id and comp.symbol_id not in unique_symbols:
                try:
                    unique_symbols[comp.symbol_id] = get_symbol_info(comp.symbol_id)
                except Exception as e:
                    logger.warning(f"Could not load symbol {comp.symbol_id}: {e}")
        return unique_symbols

    def _layout_single_sheet(
        self,
        sheet_id: str,
        source_components: List[SourceComponent],
        source_groups: List[SourceGroup],
        element_to_sheet: Dict[str, str],
        ports_by_comp: Dict[str, List[SourcePort]],
        sheet_connectivity: Dict[str, List[Dict[str, Any]]],
        generated_elements: List[CircuitElement],
        unique_symbols: Dict[str, SymbolInfo]
    ) -> List[CircuitElement]:
        sheet_source_comps = [c for c in source_components if element_to_sheet.get(c.source_component_id) == sheet_id]
        sheet_source_groups = [g for g in source_groups if element_to_sheet.get(g.source_group_id) == sheet_id and not g.is_subcircuit]
        child_sheet_groups = [g for g in source_groups if element_to_sheet.get(g.source_group_id) == sheet_id and g.is_subcircuit]

        # Skip empty sheets unless they have labels/pins
        if not sheet_source_comps and not sheet_source_groups and not child_sheet_groups:
            has_labels = any(
                e.sheet_id == sheet_id 
                for e in generated_elements 
                if isinstance(e, (SchematicHierarchicalLabel, SchematicNetLabel))
            )
            if not has_labels:
                return []

        try:
            # Build ELK Graph
            elk_graph = self.builder.build_sheet_graph(
                sheet_id, sheet_source_comps, child_sheet_groups,
                ports_by_comp, sheet_connectivity[sheet_id], generated_elements, unique_symbols
            )

            # Debug Dumps (controlled by CIRCUITWEAVER_DEBUG_ELK env var)
            if DEBUG_ELK:
                debug_input = f"debug_elk_in_{sheet_id}.json"
                Path(debug_input).write_text(json.dumps(elk_graph, indent=2))

            # Run ELK
            layout_data = self.runner.run(elk_graph)

            if DEBUG_ELK and sheet_id == "root":
                Path("debug_elk_out_root.json").write_text(json.dumps(layout_data, indent=2))

            # Parse Results
            return self.parser.parse_sheet_layout(
                sheet_id, layout_data, sheet_source_comps, ports_by_comp,
                generated_elements, unique_symbols
            )

        except Exception as e:
            logger.error(f"Layout failed for sheet {sheet_id}: {e}", exc_info=True)
            return []

    def _map_elements(self, components: List[SourceComponent], groups: List[SourceGroup]) -> Tuple[Dict[str, str], Dict[str, str]]:
        element_to_sheet = {}
        element_to_group = {}
        group_map = {g.source_group_id: g for g in groups}
        
        def get_owner_sheet(gid: Optional[str]) -> str:
            if not gid or gid not in group_map: 
                return "root"
            g = group_map[gid]
            return g.source_group_id if g.is_subcircuit else get_owner_sheet(g.parent_source_group_id)
            
        for c in components:
            pid = c.source_group_id or c.subcircuit_id
            if pid and pid not in group_map:
                match = next((g for g in groups if g.subcircuit_id == pid), None)
                if match: 
                    pid = match.source_group_id
            element_to_sheet[c.source_component_id] = get_owner_sheet(pid)
            element_to_group[c.source_component_id] = pid or "root"
            
        for g in groups:
            element_to_sheet[g.source_group_id] = get_owner_sheet(g.parent_source_group_id)
            element_to_group[g.source_group_id] = g.parent_source_group_id or "root"
            
        return element_to_sheet, element_to_group

    def _process_connectivity(
        self, 
        traces: List[SourceTrace], 
        ports: List[SourcePort], 
        nets: List[SourceNet], 
        element_to_sheet: Dict[str, str], 
        element_to_group: Dict[str, str], 
        groups: List[SourceGroup],
        elements: List[CircuitElement]
    ) -> Tuple[List[CircuitElement], Dict[str, List[Dict[str, Any]]]]:
        generated: List[CircuitElement] = []
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
            
            net_name = f"NET_{raw_name}"
            hier_name = f"HPIN_{raw_name}"

            nets_to_ports[(net_id, net_name, hier_name)].extend(involved_ports)

            for sid in {element_to_sheet.get(p.source_component_id, "root") for p in involved_ports}:
                ports_in_sheet = [p for p in involved_ports if element_to_sheet.get(p.source_component_id) == sid]
                sheet_connectivity[sid].append({
                    "trace_id": trace.source_trace_id, 
                    "net_id": net_id,
                    "ports": [p.source_port_id for p in ports_in_sheet],
                    "is_inter_group": False,
                    "is_inter_sheet": False,
                    "hpin_id": None
                })

        for (net_id, net_name, hier_name), involved_ports in nets_to_ports.items():
            involved_sheets = {element_to_sheet.get(p.source_component_id, "root") for p in involved_ports}
            is_global = any(global_name in net_name.upper() for global_name in ["GND", "5V", "3V3"])

            sheet_to_hpin_id = {}
            if len(involved_sheets) > 1 and not is_global:
                for sid in involved_sheets:
                    if sid == "root": continue
                    curr = sid
                    while curr != "root":
                        parent = element_to_sheet.get(curr, "root")
                        hpin_id = f"hpin_{net_id}_{curr}"

                        # Check if it already exists (manually or auto-generated)
                        exists = any(
                            (isinstance(e, SchematicHierarchicalPin) and e.schematic_hierarchical_pin_id == hpin_id)
                            for e in elements + generated
                        )

                        if not exists:
                            # Use hier_name for hierarchical pins/labels (cleaner, e.g., "RESET" instead of "NET_RESET_NET")
                            generated.append(SchematicHierarchicalPin(
                                schematic_hierarchical_pin_id=hpin_id,
                                sheet_id=parent, source_net_id=net_id,
                                schematic_box_id=f"box_{curr}", center=Point(x=0, y=0), text=hier_name
                            ))
                            # Always generate a label for the hpin on the parent sheet to connect it to its net
                            generated.append(SchematicNetLabel(
                                schematic_net_label_id=f"nlabel_{hpin_id}",
                                sheet_id=parent, source_net_id=net_id,
                                schematic_hierarchical_pin_id=hpin_id,
                                center=Point(x=0, y=0), text=net_name
                            ))
                            
                            ports_in_curr = [p for p in involved_ports if element_to_sheet.get(p.source_component_id) == curr]
                            bound_id = f"hlabel_bound_{net_id}_{curr}"
                            if not any(get_element_id(e) == bound_id for e in elements + generated if isinstance(e, SchematicHierarchicalLabel)):
                                generated.append(SchematicHierarchicalLabel(
                                    schematic_hierarchical_label_id=bound_id,
                                    sheet_id=curr, source_net_id=net_id,
                                    source_port_id=ports_in_curr[0].source_port_id if ports_in_curr else None,
                                    center=Point(x=0, y=0), text=hier_name
                                ))
                        sheet_to_hpin_id[curr] = hpin_id
                        curr = parent

            for sid in involved_sheets:
                ports_in_sheet = [p for p in involved_ports if element_to_sheet.get(p.source_component_id) == sid]
                involved_groups = {element_to_group.get(p.source_component_id, "root") for p in ports_in_sheet}
                
                # A sheet is labeled if:
                # 1. Multiple groups are involved in the net within this sheet
                # 2. It is a global net (GND, 3V3, etc.)
                # 3. It connects to a hierarchical pin (external connection)
                has_hpin = sid in sheet_to_hpin_id or any(sid == element_to_sheet.get(sub_sid) for sub_sid in sheet_to_hpin_id)
                is_labeled = (len(involved_groups) > 1) or is_global or has_hpin

                for conn in sheet_connectivity[sid]:
                    if conn["net_id"] == net_id:
                        conn["is_inter_group"] = is_labeled
                        conn["is_inter_sheet"] = len(involved_sheets) > 1
                        conn["hpin_id"] = sheet_to_hpin_id.get(sid)

                if is_labeled:
                    for p in ports_in_sheet:
                        lbl_id = f"nlabel_{net_id}_{p.source_port_id}"
                        if not any(get_element_id(e) == lbl_id for e in generated):
                            generated.append(SchematicNetLabel(
                                schematic_net_label_id=lbl_id,
                                sheet_id=sid, source_net_id=net_id,
                                source_port_id=p.source_port_id, center=Point(x=0, y=0), text=net_name
                            ))

        return generated, sheet_connectivity

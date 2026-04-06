import json
import logging
from collections import defaultdict
from pathlib import Path
import os
from typing import Any, Dict, List, Optional, Tuple

from circuitweaver.library.pinout import get_symbol_info, SymbolInfo
from circuitweaver.types.circuit_json import (
    CircuitElement, Point, SchematicHierarchicalLabel, SchematicNetLabel, 
    SchematicNoConnect, SourceComponent, SourceGroup, SourceNet, 
    SourcePort, SourceTrace, SchematicHierarchicalPin, get_element_id
)
from ..elk_runner import ElkRunner
from .models import LayoutNode
from .registry import MappingRegistry, LayoutContext
from .plugins.elk_layered import ElkLayeredPlugin
from .plugins.attachment import AttachmentPlugin

logger = logging.getLogger(__name__)

DEBUG_ELK = os.environ.get("CIRCUITWEAVER_DEBUG_ELK", "").lower() in ("1", "true", "yes")

class AutoLayoutEngine:
    """Orchestrates hierarchical layout using a plugin-based architecture."""

    def __init__(self, helper_path: Optional[str] = None):
        self.runner = ElkRunner(helper_path=Path(helper_path) if helper_path else None)
        self.plugins = [
            ElkLayeredPlugin(),
            AttachmentPlugin()
        ]

    def layout(self, elements: List[CircuitElement]) -> List[CircuitElement]:
        source_components = [e for e in elements if isinstance(e, SourceComponent)]
        source_groups = [e for e in elements if isinstance(e, SourceGroup)]
        source_ports = [e for e in elements if isinstance(e, SourcePort)]
        source_traces = [e for e in elements if isinstance(e, SourceTrace)]
        source_nets = [e for e in elements if isinstance(e, SourceNet)]
        
        if not source_components:
            return elements

        # 1. Map to sheets and load symbols
        element_to_sheet, element_to_group = self._map_elements(source_components, source_groups, source_ports)
        subcircuit_ids = {g.source_group_id for g in source_groups if g.is_subcircuit}
        all_sheet_ids = {"root"} | subcircuit_ids
        symbol_map = self._load_symbols(source_components)

        # 2. Connectivity Pre-processing (labels/pins)
        connectivity_elements, sheet_connectivity = self._process_connectivity(
            source_traces, source_ports, source_nets, element_to_sheet, element_to_group, source_groups, elements
        )
        
        final_positioned_elements: List[CircuitElement] = []

        # 3. Sheet-by-Sheet Plugin Execution
        for sheet_id in all_sheet_ids:
            # Elements INSIDE this sheet (Components, Ports, Labels, etc.)
            def get_strict_sheet(e: CircuitElement) -> str:
                if hasattr(e, "sheet_id"):
                    return getattr(e, "sheet_id")
                eid = get_element_id(e)
                if eid in element_to_sheet:
                    return element_to_sheet[eid]
                raise ValueError(f"Element {eid} ({type(e)}) has no sheet assignment and no sheet_id attribute.")

            sheet_elements = [
                e for e in (elements + connectivity_elements)
                if (not isinstance(e, (SourceGroup, SourceTrace, SourceNet))) and \
                   get_strict_sheet(e) == sheet_id
            ]
            
            # Boxes (child subcircuits) that appear ON this sheet
            sheet_boxes = [
                g for g in source_groups 
                if g.is_subcircuit and element_to_sheet.get(g.source_group_id) == sheet_id
            ]
            
            if not sheet_elements and not sheet_boxes:
                continue

            registry = MappingRegistry()
            # Root node options for ELK
            root_node = LayoutNode(id=sheet_id, layoutOptions={
                "org.eclipse.elk.algorithm": "layered",
                "org.eclipse.elk.padding": "[top=100,left=100,bottom=100,right=100]"
            })
            
            context = LayoutContext(
                sheet_id=sheet_id, 
                elements=sheet_elements + sheet_boxes, 
                root_node=root_node, 
                registry=registry, 
                symbol_map=symbol_map,
                sheet_connectivity=sheet_connectivity
            )

            # Build phase
            for plugin in self.plugins:
                plugin.build(context)

            # Run ELK
            elk_dict = root_node.model_dump()
            if DEBUG_ELK:
                Path(f"debug_elk_in_{sheet_id}.json").write_text(json.dumps(elk_dict, indent=2))
            
            layout_results = self.runner.run(elk_dict)

            if DEBUG_ELK:
                Path(f"debug_elk_out_{sheet_id}.json").write_text(json.dumps(layout_results, indent=2))

            # Apply phase
            for plugin in self.plugins:
                final_positioned_elements.extend(plugin.apply(context, layout_results))

        # Filter out any duplicate logical elements
        schematic_results = [
            e for e in final_positioned_elements 
            if e.type.startswith("schematic_")
        ]

        return elements + connectivity_elements + schematic_results

    def _map_elements(self, components, groups, ports):
        element_to_sheet = {}
        element_to_group = {}
        group_map = {g.source_group_id: g for g in groups}
        
        def get_owner_sheet(gid: Optional[str]) -> str:
            if not gid or gid not in group_map: return "root"
            g = group_map[gid]
            return g.source_group_id if g.is_subcircuit else get_owner_sheet(g.parent_source_group_id)
            
        for c in components:
            pid = c.source_group_id or c.subcircuit_id
            if pid and pid not in group_map:
                match = next((g for g in groups if g.subcircuit_id == pid), None)
                if match: pid = match.source_group_id
            
            sheet = get_owner_sheet(pid)
            element_to_sheet[c.source_component_id] = sheet
            element_to_group[c.source_component_id] = pid or "root"
            
            # Map ports of this component to the same sheet
            for p in ports:
                if p.source_component_id == c.source_component_id:
                    element_to_sheet[p.source_port_id] = sheet
            
        for g in groups:
            # The box for a group belongs to the parent group's owner sheet.
            element_to_sheet[g.source_group_id] = get_owner_sheet(g.parent_source_group_id)
            element_to_group[g.source_group_id] = g.parent_source_group_id or "root"
            
        return element_to_sheet, element_to_group

    def _load_symbols(self, components):
        FTYPE_MAP = {
            "simple_resistor": "Device:R",
            "simple_capacitor": "Device:C",
            "simple_led": "Device:LED",
            "simple_diode": "Device:D",
            "simple_transistor": "Device:Q_NPN_BCE",
        }
        unique_symbols = {}
        for comp in components:
            if not comp.symbol_id and comp.ftype in FTYPE_MAP:
                comp.symbol_id = FTYPE_MAP[comp.ftype]
            if comp.symbol_id and comp.symbol_id not in unique_symbols:
                try:
                    unique_symbols[comp.symbol_id] = get_symbol_info(comp.symbol_id)
                except Exception as e:
                    logger.warning(f"Could not load symbol {comp.symbol_id}: {e}")
        return unique_symbols

    def _process_connectivity(self, traces, ports, nets, element_to_sheet, element_to_group, groups, elements):
        generated = []
        sheet_connectivity = defaultdict(list)
        port_map = {p.source_port_id: p for p in ports}
        net_map = {n.source_net_id: n for n in nets}

        nets_to_ports = defaultdict(list)
        for trace in traces:
            involved_ports = [port_map[pid] for pid in trace.connected_source_port_ids if pid in port_map]
            if not involved_ports: continue
            net_id = trace.connected_source_net_ids[0] if trace.connected_source_net_ids else trace.source_trace_id
            raw_name = net_map[net_id].name if (trace.connected_source_net_ids and net_id in net_map) else trace.source_trace_id
            net_name, hier_name = f"NET_{raw_name}", f"HPIN_{raw_name}"
            nets_to_ports[(net_id, net_name, hier_name)].extend(involved_ports)

            # Record connectivity for each sheet involved
            involved_sheets = {element_to_sheet[p.source_port_id] for p in involved_ports if p.source_port_id in element_to_sheet}
            for sid in involved_sheets:
                ports_in_sheet = [p for p in involved_ports if element_to_sheet.get(p.source_port_id) == sid]
                sheet_connectivity[sid].append({
                    "trace_id": trace.source_trace_id, "net_id": net_id,
                    "ports": [p.source_port_id for p in ports_in_sheet],
                    "is_inter_group": False, "is_inter_sheet": False, "hpin_id": None
                })

        for (net_id, net_name, hier_name), involved_ports in nets_to_ports.items():
            involved_sheets = {element_to_sheet[p.source_port_id] for p in involved_ports if p.source_port_id in element_to_sheet}
            is_global = any(global_name in net_name.upper() for global_name in ["GND", "5V", "3V3"])
            sheet_to_hpin_id = {}
            
            if len(involved_sheets) > 1 and not is_global:
                for sid in involved_sheets:
                    if sid == "root": continue
                    curr = sid
                    while curr != "root":
                        parent = element_to_sheet.get(curr, "root")
                        hpin_id = f"hpin_{net_id}_{curr}"
                        if not any((isinstance(e, SchematicHierarchicalPin) and e.schematic_hierarchical_pin_id == hpin_id) for e in elements + generated):
                            generated.append(SchematicHierarchicalPin(schematic_hierarchical_pin_id=hpin_id, sheet_id=parent, source_net_id=net_id, schematic_box_id=f"box_{curr}", center=Point(x=0, y=0), text=hier_name))
                            generated.append(SchematicNetLabel(schematic_net_label_id=f"nlabel_{hpin_id}", sheet_id=parent, source_net_id=net_id, schematic_hierarchical_pin_id=hpin_id, center=Point(x=0, y=0), text=net_name))
                            ports_in_curr = [p for p in involved_ports if element_to_sheet.get(p.source_port_id) == curr]
                            bound_id = f"hlabel_bound_{net_id}_{curr}"
                            if not any(get_element_id(e) == bound_id for e in elements + generated if isinstance(e, SchematicHierarchicalLabel)):
                                generated.append(SchematicHierarchicalLabel(schematic_hierarchical_label_id=bound_id, sheet_id=curr, source_net_id=net_id, source_port_id=ports_in_curr[0].source_port_id if ports_in_curr else None, center=Point(x=0, y=0), text=hier_name))
                        sheet_to_hpin_id[curr] = hpin_id
                        curr = parent
            
            for sid in involved_sheets:
                ports_in_sheet = [p for p in involved_ports if element_to_sheet.get(p.source_port_id) == sid]
                involved_groups = {element_to_group.get(p.source_component_id, "root") for p in ports_in_sheet}
                is_labeled = (len(involved_groups) > 1) or is_global or (sid in sheet_to_hpin_id)
                for conn in sheet_connectivity[sid]:
                    if conn["net_id"] == net_id:
                        conn["is_inter_group"] = is_labeled
                        conn["is_inter_sheet"] = len(involved_sheets) > 1
                        conn["hpin_id"] = sheet_to_hpin_id.get(sid)
                if is_labeled:
                    for p in ports_in_sheet:
                        lbl_id = f"nlabel_{net_id}_{p.source_port_id}"
                        if not any(get_element_id(e) == lbl_id for e in generated):
                            generated.append(SchematicNetLabel(schematic_net_label_id=lbl_id, sheet_id=sid, source_net_id=net_id, source_port_id=p.source_port_id, center=Point(x=0, y=0), text=net_name))
        return generated, sheet_connectivity

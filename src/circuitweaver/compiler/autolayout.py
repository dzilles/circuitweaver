"""Auto-layout engine using ELK (via elkjs) with hierarchical multi-sheet support."""

import json
import logging
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from circuitweaver.library.pinout import get_symbol_info, SymbolInfo
from circuitweaver.types.circuit_json import (
    CircuitElement,
    Point,
    SchematicBox,
    SchematicComponent,
    SchematicHierarchicalLabel,
    SchematicHierarchicalPin,
    SchematicNetLabel,
    SchematicPort,
    SchematicTrace,
    SchematicTraceEdge,
    SourceComponent,
    SourceGroup,
    SourceNet,
    SourcePort,
    SourceTrace,
    get_element_id,
)

logger = logging.getLogger(__name__)

# KiCad standard grid is 50mils (10 units in our system)
KICAD_GRID_UNITS = 10

# Title block exclusion area (approx bottom-right)
TB_WIDTH = 1417
TB_HEIGHT = 354


class AutoLayoutEngine:
    """Engine for generating hierarchical multi-sheet schematic layouts."""

    def __init__(self, helper_path: Optional[str] = None):
        if helper_path:
            self.helper_path = Path(helper_path)
        else:
            self.helper_path = Path(__file__).parent / "layout_helper.js"

    def layout(self, elements: List[CircuitElement]) -> List[CircuitElement]:
        """Generate hierarchical layout for the given circuit elements."""
        source_components = [e for e in elements if isinstance(e, SourceComponent)]
        source_ports = [e for e in elements if isinstance(e, SourcePort)]
        source_traces = [e for e in elements if isinstance(e, SourceTrace)]
        source_groups = [e for e in elements if isinstance(e, SourceGroup)]
        source_nets = [e for e in elements if isinstance(e, SourceNet)]

        if not source_components:
            return elements

        # 1. Map elements to sheets and subgroups
        element_to_sheet, element_to_group = self._map_elements(source_components, source_groups)
        subcircuit_group_ids = {g.source_group_id for g in source_groups if g.is_subcircuit}
        all_sheet_ids = {"root"} | subcircuit_group_ids

        # 2. Gather symbols
        unique_symbols: Dict[str, SymbolInfo] = {}
        for comp in source_components:
            if comp.symbol_id and comp.symbol_id not in unique_symbols:
                try:
                    unique_symbols[comp.symbol_id] = get_symbol_info(comp.symbol_id)
                except Exception: pass

        # 3. Analyze Connectivity (Inter-sheet and Inter-group)
        connectivity_elements, sheet_connectivity = self._process_connectivity(
            source_traces, source_ports, source_nets, element_to_sheet, element_to_group, source_groups, source_components
        )

        final_schematic_elements: List[CircuitElement] = []
        final_schematic_elements.extend(connectivity_elements)

        # 4. Sheet Layout Pass
        comp_origins: Dict[str, Point] = {}
        positioned_elements: List[CircuitElement] = []

        for sheet_id in all_sheet_ids:
            sheet_source_comps = [c for c in source_components if element_to_sheet.get(c.source_component_id) == sheet_id]
            sheet_source_groups = [g for g in source_groups if element_to_sheet.get(g.source_group_id) == sheet_id]
            child_sheet_groups = [
                g for g in source_groups 
                if g.is_subcircuit and (
                    (g.parent_source_group_id == sheet_id) or 
                    (sheet_id == "root" and not g.parent_source_group_id)
                )
            ]

            if not sheet_source_comps and not sheet_source_groups and not child_sheet_groups:
                has_labels = any(e.sheet_id == sheet_id for e in connectivity_elements if isinstance(e, (SchematicHierarchicalLabel, SchematicNetLabel)))
                if not has_labels: continue

            elk_graph = self._build_sheet_elk_graph(
                sheet_id, sheet_source_comps, sheet_source_groups, child_sheet_groups,
                source_ports, sheet_connectivity[sheet_id], connectivity_elements, unique_symbols
            )

            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                input_file = tmp_path / f"elk_{sheet_id}_in.json"
                output_file = tmp_path / f"elk_{sheet_id}_out.json"
                input_file.write_text(json.dumps(elk_graph))

                try:
                    subprocess.run(["node", str(self.helper_path), str(input_file), str(output_file)], check=True, capture_output=True, text=True)
                    layout_data = json.loads(output_file.read_text())
                    
                    sheet_results = self._parse_sheet_layout(
                        sheet_id, layout_data, sheet_source_comps, source_ports, 
                        sheet_source_groups, child_sheet_groups, connectivity_elements, unique_symbols
                    )
                    positioned_elements.extend(sheet_results)
                    for e in sheet_results:
                        if isinstance(e, SchematicComponent): comp_origins[e.source_component_id] = e.center
                except Exception as e:
                    logger.error(f"Layout failed for {sheet_id}: {e}")

        # 5. Snap Labels to Pins
        self._snap_labels(connectivity_elements, comp_origins, source_ports, unique_symbols, source_components)

        return elements + positioned_elements + connectivity_elements

    def _map_elements(self, components, groups):
        element_to_sheet = {}
        element_to_group = {}
        group_map = {g.source_group_id: g for g in groups}
        
        def get_owner_sheet(gid):
            if not gid or gid not in group_map: return "root"
            g = group_map[gid]
            return g.source_group_id if g.is_subcircuit else get_owner_sheet(g.parent_source_group_id)
            
        for c in components:
            pid = c.source_group_id or c.subcircuit_id
            if pid and pid not in group_map:
                match = next((g for g in groups if g.subcircuit_id == pid), None)
                if match: pid = match.source_group_id
            element_to_sheet[c.source_component_id] = get_owner_sheet(pid)
            element_to_group[c.source_component_id] = pid or "root"
            
        for g in groups:
            element_to_sheet[g.source_group_id] = get_owner_sheet(g.parent_source_group_id)
            element_to_group[g.source_group_id] = g.parent_source_group_id or "root"
            
        return element_to_sheet, element_to_group

    def _process_connectivity(self, traces, ports, nets, element_to_sheet, element_to_group, groups, components):
        generated = []
        sheet_connectivity = defaultdict(list)
        port_map = {p.source_port_id: p for p in ports}
        net_map = {n.source_net_id: n for n in nets}
        
        for trace in traces:
            involved_ports = [port_map[pid] for pid in trace.connected_source_port_ids if pid in port_map]
            if not involved_ports: continue
            
            involved_sheets = {element_to_sheet.get(p.source_component_id, "root") for p in involved_ports}
            net_name = net_map[trace.connected_source_net_ids[0]].name if trace.connected_source_net_ids else f"NET_{trace.source_trace_id}"
            
            if len(involved_sheets) > 1:
                for p in involved_ports:
                    sid = element_to_sheet.get(p.source_component_id, "root")
                    if sid == "root": continue
                    generated.append(SchematicHierarchicalLabel(
                        schematic_hierarchical_label_id=f"hlabel_{trace.source_trace_id}_{p.source_port_id}",
                        sheet_id=sid, source_net_id=trace.connected_source_net_ids[0] if trace.connected_source_net_ids else "logic",
                        source_port_id=p.source_port_id, center=Point(x=0, y=0), text=net_name
                    ))
                    psid = element_to_sheet.get(sid, "root")
                    generated.append(SchematicHierarchicalPin(
                        schematic_hierarchical_pin_id=f"hpin_{trace.source_trace_id}_{sid}",
                        sheet_id=psid, source_net_id=trace.connected_source_net_ids[0] if trace.connected_source_net_ids else "logic",
                        schematic_box_id=f"box_{sid}", center=Point(x=0, y=0), text=net_name
                    ))

            for sid in involved_sheets:
                ports_in_sheet = [p for p in involved_ports if element_to_sheet.get(p.source_component_id) == sid]
                involved_groups = {element_to_group.get(p.source_component_id, "root") for p in ports_in_sheet}
                
                is_labeled = len(involved_groups) > 1
                if is_labeled:
                    for p in ports_in_sheet:
                        generated.append(SchematicNetLabel(
                            schematic_net_label_id=f"nlabel_{trace.source_trace_id}_{p.source_port_id}",
                            sheet_id=sid, source_net_id=trace.connected_source_net_ids[0] if trace.connected_source_net_ids else "logic",
                            source_port_id=p.source_port_id, center=Point(x=0, y=0), text=net_name
                        ))
                
                sheet_connectivity[sid].append({
                    "trace_id": trace.source_trace_id, 
                    "net_id": trace.connected_source_net_ids[0] if trace.connected_source_net_ids else None, 
                    "ports": [p.source_port_id for p in ports_in_sheet],
                    "is_inter_group": is_labeled,
                    "is_inter_sheet": len(involved_sheets) > 1
                })
                
        return generated, sheet_connectivity

    def _build_sheet_elk_graph(self, sheet_id, components, subgroups, child_sheets, all_ports, connectivity, generated, symbol_map):
        nodes = []
        for item in components:
            symbol = symbol_map.get(item.symbol_id)
            width, height = (symbol.width, symbol.height) if symbol else (40, 40)
            ports = []
            for p in [p for p in all_ports if p.source_component_id == item.source_component_id]:
                pi = None
                if symbol: pi = next((pin for pin in symbol.pins if pin.number == str(p.pin_number)), None) or next((pin for pin in symbol.pins if pin.name == p.name), None)
                px, py = (pi.grid_offset.x - symbol.bounding_box_min.x, pi.grid_offset.y - symbol.bounding_box_min.y) if pi and symbol else (0, 0)
                side = {"left": "EAST", "right": "WEST", "up": "SOUTH", "down": "NORTH"}.get(pi.direction if pi else "right", "WEST")
                ports.append({"id": p.source_port_id, "x": px, "y": py, "width": 0, "height": 0, "layoutOptions": {"org.eclipse.elk.port.side": side}})
            nodes.append({"id": item.source_component_id, "width": width, "height": height, "ports": ports, "layoutOptions": {"org.eclipse.elk.portConstraints": "FIXED_POS"}})
        
        for cs in child_sheets:
            bid = f"box_{cs.source_group_id}"; pins = [e for e in generated if isinstance(e, SchematicHierarchicalPin) and e.schematic_box_id == bid]
            bw = max(150, max((len(p.text) for p in pins), default=0) * 10 + 60); bh = max(80, len(pins) * 20 + 40)
            ports = [{"id": p.schematic_hierarchical_pin_id, "width": 0, "height": 0, "layoutOptions": {"org.eclipse.elk.port.side": "WEST"}} for p in pins]
            nodes.append({"id": bid, "width": bw, "height": bh, "ports": ports, "labels": [{"text": cs.name or cs.source_group_id}], "layoutOptions": {"org.eclipse.elk.portConstraints": "FREE"}})
        
        edges = []
        for conn in connectivity:
            sip = conn["ports"]
            if not sip: continue
            if not conn["is_inter_group"] and not conn["is_inter_sheet"]:
                for target in sip[1:]: edges.append({"id": f"e_{conn['trace_id']}_{target}", "sources": [sip[0]], "targets": [target]})
            
        options = {"org.eclipse.elk.algorithm": "layered", "org.eclipse.elk.spacing.nodeNode": "150", "org.eclipse.elk.layered.spacing.nodeNodeBetweenLayers": "200"}
        if sheet_id == "root": options["org.eclipse.elk.padding"] = f"[top=100,left=100,bottom={TB_HEIGHT + 100},right={TB_WIDTH + 100}]"
        return {"id": sheet_id, "children": nodes, "ports": [], "edges": edges, "layoutOptions": options}

    def _parse_sheet_layout(self, sheet_id, data, components, all_ports, subgroups, child_sheets, generated, symbol_map):
        results = []
        def snap(v): return float(round(v / KICAD_GRID_UNITS) * KICAD_GRID_UNITS)
        for node in data.get("children", []):
            cid = node["id"]
            nx, ny = snap(node["x"]), snap(node["y"])
            if cid.startswith("box_"):
                results.append(SchematicBox(schematic_box_id=cid, sheet_id=sheet_id, x=nx, y=ny, width=snap(node["width"]), height=snap(node["height"]), is_hierarchical_sheet=True))
                for p in node.get("ports", []):
                    hp = next((e for e in generated if isinstance(e, SchematicHierarchicalPin) and e.schematic_hierarchical_pin_id == p["id"]), None)
                    if hp: hp.center = Point(x=snap(nx + p["x"]), y=snap(ny + p["y"]))
            else:
                comp = next((c for c in components if c.source_component_id == cid), None)
                if comp:
                    sym = symbol_map.get(comp.symbol_id); off = sym.bounding_box_min if sym else Point(x=0, y=0)
                    results.append(SchematicComponent(schematic_component_id=f"sch_{cid}", sheet_id=sheet_id, source_component_id=cid, center=Point(x=nx - off.x, y=ny - off.y)))
        for edge in data.get("edges", []):
            for sec in edge.get("sections", []):
                pts = [Point(x=snap(sec["startPoint"]["x"]), y=snap(sec["startPoint"]["y"]))]
                pts.extend([Point(x=snap(bp["x"]), y=snap(bp["y"])) for bp in sec.get("bendPoints", [])])
                pts.append(Point(x=snap(sec["endPoint"]["x"]), y=snap(sec["endPoint"]["y"])))
                el = []
                for i in range(len(pts)-1):
                    if pts[i].x != pts[i+1].x or pts[i].y != pts[i+1].y: el.append(SchematicTraceEdge.model_validate({"from": pts[i], "to": pts[i+1]}))
                if el: results.append(SchematicTrace(schematic_trace_id=f"sch_{edge['id']}", sheet_id=sheet_id, edges=el))
        return results

    def _snap_labels(self, generated, comp_origins, source_ports, symbols, source_components):
        """Final Pass: Match EVERY label to the EXACT pin coordinate."""
        port_to_parent = {p.source_port_id: p for p in source_ports}
        comp_map = {c.source_component_id: c for c in source_components}
        
        for lbl in [e for e in generated if isinstance(e, (SchematicHierarchicalLabel, SchematicNetLabel))]:
            if not lbl.source_port_id: continue
            port = port_to_parent.get(lbl.source_port_id)
            if not port: continue
            origin = comp_origins.get(port.source_component_id)
            if not origin: continue
            comp = comp_map.get(port.source_component_id)
            if not comp: continue
            symbol = symbols.get(comp.symbol_id)
            if not symbol: continue
            
            pi = next((pin for pin in symbol.pins if pin.number == str(port.pin_number)), None) or \
                 next((pin for pin in symbol.pins if pin.name == port.name), None)
            
            if pi:
                lbl.center = Point(x=origin.x + pi.grid_offset.x, y=origin.y + pi.grid_offset.y)
                # Flip anchor based on pin direction so text doesn't overlap component
                if isinstance(lbl, SchematicNetLabel):
                    lbl.anchor_side = {"left": "right", "right": "left", "up": "bottom", "down": "top"}.get(pi.direction, "left")

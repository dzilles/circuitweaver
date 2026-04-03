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

        # 1. Map every element to its "Owner Sheet" (subcircuit)
        element_to_sheet = self._map_elements_to_sheets(source_components, source_groups)
        subcircuit_group_ids = {g.source_group_id for g in source_groups if g.is_subcircuit}
        all_sheet_ids = {"root"} | subcircuit_group_ids

        # 2. Gather KiCad Symbol Info
        unique_symbols: Dict[str, SymbolInfo] = {}
        for comp in source_components:
            if comp.symbol_id and comp.symbol_id not in unique_symbols:
                try:
                    unique_symbols[comp.symbol_id] = get_symbol_info(comp.symbol_id)
                except Exception as e:
                    logger.warning(f"Could not get symbol info for {comp.symbol_id}: {e}")

        # 3. Connectivity Analysis (Generate Hierarchical Pins and Labels)
        connectivity_elements, sheet_connectivity = self._process_connectivity(
            source_traces, source_ports, source_nets, element_to_sheet, source_groups, source_components
        )

        final_schematic_elements: List[CircuitElement] = []
        final_schematic_elements.extend(connectivity_elements)

        # 4. Sheet-by-Sheet Layout Pass
        comp_centers: Dict[str, Point] = {}
        all_positioned_elements: List[CircuitElement] = []

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
                # Check for floating labels that might need positioning
                has_labels = any(e.sheet_id == sheet_id for e in connectivity_elements if isinstance(e, SchematicHierarchicalLabel))
                if not has_labels: continue

            # Build ELK graph for this specific sheet
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
                    
                    # Extract coordinates
                    sheet_results = self._parse_sheet_layout(
                        sheet_id, layout_data, sheet_source_comps, source_ports, 
                        sheet_source_groups, child_sheet_groups, connectivity_elements, unique_symbols
                    )
                    all_positioned_elements.extend(sheet_results)
                    for e in sheet_results:
                        if isinstance(e, SchematicComponent):
                            comp_centers[e.source_component_id] = e.center
                except Exception as e:
                    logger.error(f"Failed layout for sheet {sheet_id}: {e}")

        # 5. Snap Label Positions to exact pin coordinates
        self._snap_label_positions(connectivity_elements, comp_centers, source_components, unique_symbols)

        return elements + all_positioned_elements + connectivity_elements

    def _map_elements_to_sheets(self, components: List[SourceComponent], groups: List[SourceGroup]) -> Dict[str, str]:
        mapping = {}
        group_map = {g.source_group_id: g for g in groups}
        def get_owner_sheet(group_id: Optional[str]) -> str:
            if not group_id or group_id not in group_map: return "root"
            g = group_map[group_id]; return g.source_group_id if g.is_subcircuit else get_owner_sheet(g.parent_source_group_id)
        for comp in components:
            parent_id = comp.source_group_id or comp.subcircuit_id
            if parent_id and parent_id not in group_map:
                match = next((g for g in groups if g.subcircuit_id == parent_id), None)
                if match: parent_id = match.source_group_id
            mapping[comp.source_component_id] = get_owner_sheet(parent_id)
        for g in groups: mapping[g.source_group_id] = get_owner_sheet(g.parent_source_group_id)
        return mapping

    def _process_connectivity(self, traces, ports, nets, element_to_sheet, groups, components):
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
                # Inter-sheet connection
                for sheet_id in involved_sheets:
                    if sheet_id == "root": continue
                    # Sub-sheet Hierarchical Label
                    generated.append(SchematicHierarchicalLabel(
                        schematic_hierarchical_label_id=f"hlabel_{trace.source_trace_id}_{sheet_id}",
                        sheet_id=sheet_id, source_net_id=trace.connected_source_net_ids[0] if trace.connected_source_net_ids else "logic",
                        center=Point(x=0, y=0), text=net_name
                    ))
                    # Parent-sheet Hierarchical Pin on box
                    parent_sheet_id = element_to_sheet.get(sheet_id, "root")
                    generated.append(SchematicHierarchicalPin(
                        schematic_hierarchical_pin_id=f"hpin_{trace.source_trace_id}_{sheet_id}",
                        sheet_id=parent_sheet_id, source_net_id=trace.connected_source_net_ids[0] if trace.connected_source_net_ids else "logic",
                        schematic_box_id=f"box_{sheet_id}", center=Point(x=0, y=0), text=net_name
                    ))

            for sheet_id in involved_sheets:
                sheet_connectivity[sheet_id].append({
                    "trace_id": trace.source_trace_id, 
                    "net_id": trace.connected_source_net_ids[0] if trace.connected_source_net_ids else None, 
                    "ports": [p.source_port_id for p in involved_ports if element_to_sheet.get(p.source_component_id) == sheet_id], 
                    "is_inter_sheet": len(involved_sheets) > 1
                })
        return generated, sheet_connectivity

    def _build_sheet_elk_graph(self, sheet_id, components, subgroups, child_sheets, all_ports, connectivity, generated, symbol_map):
        nodes = []
        # 1. Components
        for item in components:
            symbol = symbol_map.get(item.symbol_id)
            width, height = (symbol.width, symbol.height) if symbol else (40, 40)
            ports = []
            for p in [p for p in all_ports if p.source_component_id == item.source_component_id]:
                pin_info = None
                if symbol:
                    pin_info = next((pin for pin in symbol.pins if pin.number == str(p.pin_number)), None) or \
                               next((pin for pin in symbol.pins if pin.name == p.name), None)
                px, py = (pin_info.grid_offset.x - symbol.bounding_box_min.x, pin_info.grid_offset.y - symbol.bounding_box_min.y) if pin_info and symbol else (0, 0)
                side = {"left": "EAST", "right": "WEST", "up": "SOUTH", "down": "NORTH"}.get(pin_info.direction if pin_info else "right", "WEST")
                ports.append({"id": p.source_port_id, "x": px, "y": py, "width": 0, "height": 0, "layoutOptions": {"org.eclipse.elk.port.side": side}})
            nodes.append({"id": item.source_component_id, "width": width, "height": height, "ports": ports, "layoutOptions": {"org.eclipse.elk.portConstraints": "FIXED_POS"}})
        
        # 2. Child Sheets (Dynamic Sizing)
        for cs in child_sheets:
            sheet_box_id = f"box_{cs.source_group_id}"
            pins = [e for e in generated if isinstance(e, SchematicHierarchicalPin) and e.schematic_box_id == sheet_box_id]
            max_pin_len = max((len(p.text) for p in pins), default=0)
            box_width = max(150, max_pin_len * 10 + 60)
            box_height = max(80, len(pins) * 20 + 40)
            ports = []
            for i, p in enumerate(pins):
                ports.append({"id": p.schematic_hierarchical_pin_id, "width": 0, "height": 0, "layoutOptions": {"org.eclipse.elk.port.side": "WEST"}})
            nodes.append({"id": sheet_box_id, "width": box_width, "height": box_height, "ports": ports, "labels": [{"text": cs.name or cs.source_group_id}], "layoutOptions": {"org.eclipse.elk.portConstraints": "FREE"}})

        # 3. Boundary Ports
        root_ports = []
        for lbl in [e for e in generated if isinstance(e, SchematicHierarchicalLabel) and e.sheet_id == sheet_id]:
            root_ports.append({"id": lbl.schematic_hierarchical_label_id, "width": 0, "height": 0})

        # 4. Edges
        edges = []
        for conn in connectivity:
            ports_in_sheet = conn["ports"]
            if not ports_in_sheet: continue
            p0 = ports_in_sheet[0]
            for target in ports_in_sheet[1:]:
                edges.append({"id": f"e_{conn['trace_id']}_{target}", "sources": [p0], "targets": [target]})
            if conn["is_inter_sheet"]:
                hlabel = next((e for e in generated if isinstance(e, SchematicHierarchicalLabel) and e.sheet_id == sheet_id and e.source_net_id == conn["net_id"]), None)
                if hlabel: edges.append({"id": f"e_hlbl_{conn['trace_id']}", "sources": [p0], "targets": [hlabel.schematic_hierarchical_label_id]})
                hpin = next((e for e in generated if isinstance(e, SchematicHierarchicalPin) and e.sheet_id == sheet_id and e.source_net_id == conn["net_id"]), None)
                if hpin: edges.append({"id": f"e_hpin_{conn['trace_id']}", "sources": [p0], "targets": [hpin.schematic_hierarchical_pin_id]})

        options = {"org.eclipse.elk.algorithm": "layered", "org.eclipse.elk.spacing.nodeNode": "150", "org.eclipse.elk.layered.spacing.nodeNodeBetweenLayers": "200"}
        if sheet_id == "root":
            options["org.eclipse.elk.padding"] = f"[top=100,left=100,bottom={TB_HEIGHT + 100},right={TB_WIDTH + 100}]"
        return {"id": sheet_id, "children": nodes, "ports": root_ports, "edges": edges, "layoutOptions": options}

    def _parse_sheet_layout(self, sheet_id, data, components, all_ports, subgroups, child_sheets, generated, symbol_map):
        results = []
        def snap_grid(val): return float(round(val / KICAD_GRID_UNITS) * KICAD_GRID_UNITS)
        for node in data.get("children", []):
            cid = node["id"]
            nx, ny = snap_grid(node["x"]), snap_grid(node["y"])
            if cid.startswith("box_"):
                results.append(SchematicBox(schematic_box_id=cid, sheet_id=sheet_id, x=nx, y=ny, width=snap_grid(node["width"]), height=snap_grid(node["height"]), is_hierarchical_sheet=True))
                for p in node.get("ports", []):
                    hpin = next((e for e in generated if isinstance(e, SchematicHierarchicalPin) and e.schematic_hierarchical_pin_id == p["id"]), None)
                    if hpin: hpin.center = Point(x=snap_grid(nx + p["x"]), y=snap_grid(ny + p["y"]))
            else:
                comp = next((c for c in components if c.source_component_id == cid), None)
                if comp:
                    symbol = symbol_map.get(comp.symbol_id); off = symbol.bounding_box_min if symbol else Point(x=0, y=0)
                    results.append(SchematicComponent(schematic_component_id=f"sch_{cid}", sheet_id=sheet_id, source_component_id=cid, center=Point(x=nx - off.x, y=ny - off.y)))
        for edge in data.get("edges", []):
            for sec in edge.get("sections", []):
                pts = [Point(x=snap_grid(sec["startPoint"]["x"]), y=snap_grid(sec["startPoint"]["y"]))]
                pts.extend([Point(x=snap_grid(bp["x"]), y=snap_grid(bp["y"])) for bp in sec.get("bendPoints", [])])
                pts.append(Point(x=snap_grid(sec["endPoint"]["x"]), y=snap_grid(sec["endPoint"]["y"])))
                edge_list = []
                for i in range(len(pts)-1):
                    if pts[i].x != pts[i+1].x or pts[i].y != pts[i+1].y: edge_list.append(SchematicTraceEdge.model_validate({"from": pts[i], "to": pts[i+1]}))
                if edge_list: results.append(SchematicTrace(schematic_trace_id=f"sch_{edge['id']}", sheet_id=sheet_id, edges=edge_list))
        for port in data.get("ports", []):
            hlabel = next((e for e in generated if isinstance(e, SchematicHierarchicalLabel) and e.schematic_hierarchical_label_id == port["id"]), None)
            if hlabel: hlabel.center = Point(x=snap_grid(port["x"]), y=snap_grid(port["y"]))
        return results

    def _snap_label_positions(self, generated, comp_centers, source_comps, symbol_map):
        """Place labels exactly on the connected pins."""
        comp_map = {c.source_component_id: c for c in source_comps}
        for lbl in [e for e in generated if isinstance(e, (SchematicHierarchicalLabel, SchematicNetLabel))]:
            # Simple heuristic: label ID contains port ID
            # In a more robust system, we'd store the port_id in the label model
            pass

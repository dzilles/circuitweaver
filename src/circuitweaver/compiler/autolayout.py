"""Auto-layout engine using ELK (via elkjs) with hierarchical multi-sheet support."""

import json
import logging
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, TypedDict

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
    SchematicText,
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


class ElkSizingConfig:
    CHAR_WIDTH_PX = 7
    BOX_PADDING = 120
    PIN_SPACING = 20
    MIN_BOX_W = 250
    MIN_BOX_H = 100
    TB_WIDTH = 1417
    TB_HEIGHT = 354
    LABEL_HEIGHT = 10


class ElkPort(TypedDict):
    id: str
    x: float
    y: float
    width: float
    height: float
    layoutOptions: Dict[str, str]


class ElkNode(TypedDict, total=False):
    id: str
    width: float
    height: float
    ports: List[ElkPort]
    children: List["ElkNode"]
    edges: List[Dict[str, Any]]
    layoutOptions: Dict[str, str]


class AutoLayoutEngine:
    """Engine for generating hierarchical multi-sheet schematic layouts."""

    def __init__(self, helper_path: Optional[str] = None):
        import shutil
        if not shutil.which("node"):
            raise RuntimeError("Node.js is required for schematic auto-layout but was not found.")

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
        # Map ftype to default KiCad symbols if symbol_id is missing
        FTYPE_MAP = {
            "simple_resistor": "Device:R",
            "simple_capacitor": "Device:C",
            "simple_led": "Device:LED",
            "simple_diode": "Device:D",
            "simple_transistor": "Device:Q_NPN_BCE",
        }

        for comp in source_components:
            if not comp.symbol_id and comp.ftype in FTYPE_MAP:
                comp.symbol_id = FTYPE_MAP[comp.ftype]

        unique_symbols: Dict[str, SymbolInfo] = {}
        for comp in source_components:
            if comp.symbol_id and comp.symbol_id not in unique_symbols:
                try:
                    unique_symbols[comp.symbol_id] = get_symbol_info(comp.symbol_id)
                except Exception as e:
                    logger.warning(f"Could not load symbol {comp.symbol_id}: {e}")

        # 3. Analyze Connectivity
        connectivity_elements, sheet_connectivity = self._process_connectivity(
            source_traces, source_ports, source_nets, element_to_sheet, element_to_group, source_groups, source_components
        )

        final_schematic_elements: List[CircuitElement] = []
        final_schematic_elements.extend(connectivity_elements)

        # 4. Sheet Layout Pass
        comp_origins: Dict[str, Point] = {}
        all_positioned_elements: List[CircuitElement] = []

        # O(1) Lookups for ports
        ports_by_comp = defaultdict(list)
        for p in source_ports:
            ports_by_comp[p.source_component_id].append(p)

        for sheet_id in all_sheet_ids:
            sheet_source_comps = [c for c in source_components if element_to_sheet.get(c.source_component_id) == sheet_id]
            sheet_source_groups = [g for g in source_groups if element_to_sheet.get(g.source_group_id) == sheet_id and not g.is_subcircuit]
            child_sheet_groups = [g for g in source_groups if element_to_sheet.get(g.source_group_id) == sheet_id and g.is_subcircuit]

            if not sheet_source_comps and not sheet_source_groups and not child_sheet_groups:
                has_labels = any(e.sheet_id == sheet_id for e in connectivity_elements if isinstance(e, (SchematicHierarchicalLabel, SchematicNetLabel)))
                if not has_labels: continue

            try:
                elk_graph = self._build_sheet_elk_graph(
                    sheet_id, sheet_source_comps, sheet_source_groups, child_sheet_groups,
                    ports_by_comp, sheet_connectivity[sheet_id], connectivity_elements, unique_symbols
                )

                try:
                    process = subprocess.run(
                        ["node", str(self.helper_path)],
                        input=json.dumps(elk_graph),
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    layout_data = json.loads(process.stdout)

                    if sheet_id == "root":
                        Path("debug_elk_out_root.json").write_text(process.stdout)
                except subprocess.CalledProcessError as e:
                    error_msg = e.stderr if e.stderr else e.stdout
                    logger.error(f"ELK Layout failed for {sheet_id}: {error_msg}")
                    raise RuntimeError(f"Layout failed for {sheet_id}: {error_msg}")

                sheet_results = self._parse_sheet_layout(
                    sheet_id, layout_data, sheet_source_comps, ports_by_comp, 
                    sheet_source_groups, child_sheet_groups, connectivity_elements, unique_symbols
                )

                # Validation: Check if all components were placed
                placed_comp_ids = {e.source_component_id for e in sheet_results if isinstance(e, SchematicComponent)}
                missing_comps = [c.source_component_id for c in sheet_source_comps if c.source_component_id not in placed_comp_ids]
                if missing_comps:
                    raise RuntimeError(f"Sheet {sheet_id}: Components failed to be placed by layout engine: {missing_comps}")

                for e in sheet_results:
                    if isinstance(e, SchematicComponent):
                        comp_origins[e.source_component_id] = e.center

                all_positioned_elements.extend(sheet_results)
            except Exception as e:
                if isinstance(e, RuntimeError): raise e
                raise RuntimeError(f"Layout failed for {sheet_id}: {e}")

        return elements + all_positioned_elements + connectivity_elements

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

        # Group everything by logical net
        # (net_id, net_name) -> list of ports
        nets_to_ports = defaultdict(list)
        for trace in traces:
            involved_ports = [port_map[pid] for pid in trace.connected_source_port_ids if pid in port_map]
            if not involved_ports: continue

            net_id = trace.connected_source_net_ids[0] if trace.connected_source_net_ids else trace.source_trace_id
            net_name = net_map[net_id].name if (trace.connected_source_net_ids and net_id in net_map) else f"NET_{trace.source_trace_id}"

            nets_to_ports[(net_id, net_name)].extend(involved_ports)

            # Record local connectivity for layout engine
            for sid in {element_to_sheet.get(p.source_component_id, "root") for p in involved_ports}:
                ports_in_sheet = [p for p in involved_ports if element_to_sheet.get(p.source_component_id) == sid]
                sheet_connectivity[sid].append({
                    "trace_id": trace.source_trace_id, 
                    "net_id": net_id,
                    "ports": [p.source_port_id for p in ports_in_sheet],
                    "is_inter_group": False, # Will refine below
                    "is_inter_sheet": False, # Will refine below
                    "hpin_id": None
                })

        for (net_id, net_name), involved_ports in nets_to_ports.items():
            involved_sheets = {element_to_sheet.get(p.source_component_id, "root") for p in involved_ports}

            # Phase 5: Use actual logical schema flags if available
            net_obj = net_map.get(net_id)
            if net_obj:
                is_global = net_obj.is_power or net_obj.is_ground
            else:
                # Fallback to name matching for global nets (GND, 5V, etc.)
                is_global = any(global_name in net_name.upper() for global_name in ["GND", "5V", "3V3"])

            sheet_to_hpin_id = {}
            if len(involved_sheets) > 1 and not is_global:
                for sid in involved_sheets:
                    if sid == "root": continue
                    curr = sid
                    while curr != "root":
                        parent = element_to_sheet.get(curr, "root")
                        hpin_id = f"hpin_{net_id}_{curr}"
                        if not any(e.schematic_hierarchical_pin_id == hpin_id for e in generated if isinstance(e, SchematicHierarchicalPin)):
                            generated.append(SchematicHierarchicalPin(
                                schematic_hierarchical_pin_id=hpin_id,
                                sheet_id=parent, source_net_id=net_id,
                                schematic_box_id=f"box_{curr}", center=Point(x=0, y=0), text=net_name
                            ))
                            generated.append(SchematicNetLabel(
                                schematic_net_label_id=f"nlabel_hpin_{net_id}_{curr}",
                                sheet_id=parent, source_net_id=net_id,
                                schematic_hierarchical_pin_id=hpin_id, center=Point(x=0, y=0), text=net_name
                            ))
                            ports_in_curr = [p for p in involved_ports if element_to_sheet.get(p.source_component_id) == curr]
                            # Use the same ID format for checking and creation
                            bound_id = f"hlabel_bound_{net_id}_{curr}"
                            if not any(get_element_id(e) == bound_id for e in generated if isinstance(e, SchematicHierarchicalLabel)):
                                generated.append(SchematicHierarchicalLabel(
                                    schematic_hierarchical_label_id=bound_id,
                                    sheet_id=curr, source_net_id=net_id,
                                    source_port_id=ports_in_curr[0].source_port_id if ports_in_curr else None,
                                    center=Point(x=0, y=0), text=net_name
                                ))
                        sheet_to_hpin_id[curr] = hpin_id
                        curr = parent

            # Now mark labeling requirements per sheet
            for sid in involved_sheets:
                ports_in_sheet = [p for p in involved_ports if element_to_sheet.get(p.source_component_id) == sid]
                involved_groups = {element_to_group.get(p.source_component_id, "root") for p in ports_in_sheet}

                is_labeled = (len(involved_groups) > 1) or is_global

                # Update sheet_connectivity metadata
                for conn in sheet_connectivity[sid]:
                    if conn["net_id"] == net_id:
                        conn["is_inter_group"] = is_labeled
                        conn["is_inter_sheet"] = len(involved_sheets) > 1
                        conn["hpin_id"] = sheet_to_hpin_id.get(sid)

                # Add net labels if required
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


    def _build_sheet_elk_graph(self, sheet_id: str, components: List[SourceComponent], subgroups, child_sheets, ports_by_comp: Dict[str, List[SourcePort]], connectivity, generated, symbol_map: Dict[str, SymbolInfo]) -> ElkNode:
        nodes: List[ElkNode] = []
        edges: List[Dict[str, Any]] = []
        
        sheet_labels = [e for e in generated if isinstance(e, (SchematicNetLabel, SchematicHierarchicalLabel)) and e.sheet_id == sheet_id]
        added_labels = set()

        # 1. Components
        for item in components:
            node, comp_edges = self._build_elk_component_node(item, ports_by_comp[item.source_component_id], sheet_labels, added_labels, symbol_map)
            nodes.append(node)
            edges.extend(comp_edges)
        
        # 2. Sheet Boxes
        for cs in child_sheets:
            node, box_edges = self._build_elk_box_node(cs, sheet_id, sheet_labels, added_labels, generated)
            nodes.append(node)
            edges.extend(box_edges)

        # 3. Connectivity Edges
        edges.extend(self._build_elk_connectivity_edges(connectivity, components, child_sheets, ports_by_comp, generated))
            
        options = {
            "org.eclipse.elk.algorithm": "layered",
            "org.eclipse.elk.spacing.nodeNode": "10" if sheet_id != "root" else "100",
            "org.eclipse.elk.layered.spacing.nodeNodeBetweenLayers": "40" if sheet_id != "root" else "150",
            "org.eclipse.elk.layered.nodePlacement.strategy": "BRANDES_KOEPF",
            "org.eclipse.elk.aspectRatio": "1.414",
            "org.eclipse.elk.padding": f"[top=200,left=200,bottom={ElkSizingConfig.TB_HEIGHT + 200},right={ElkSizingConfig.TB_WIDTH + 200}]"
        }
            
        return {"id": sheet_id, "children": nodes, "edges": edges, "layoutOptions": options}

    def _build_elk_component_node(self, item: SourceComponent, comp_ports: List[SourcePort], sheet_labels, added_labels, symbol_map) -> Tuple[ElkNode, List[Dict[str, Any]]]:
        symbol = symbol_map.get(item.symbol_id)
        body_w, body_h = (symbol.width, symbol.height) if symbol else (40, 40)
        body_w, body_h = max(body_w, 10), max(body_h, 10)
        
        ports: List[ElkPort] = []
        edges: List[Dict[str, Any]] = []
        symbol_pins = {p.number: p for p in symbol.pins} if symbol else {}
        
        for p in comp_ports:
            pi = symbol_pins.get(str(p.pin_number)) or next((pin for pin in symbol_pins.values() if pin.name == p.name), None)
            if pi:
                px, py = (pi.grid_offset.x - symbol.bounding_box_min.x, pi.grid_offset.y - symbol.bounding_box_min.y)
                side = {"left": "EAST", "right": "WEST", "up": "SOUTH", "down": "NORTH"}.get(pi.direction, "WEST")
            else:
                px, py = 0, 0
                side = "WEST"
            
            elk_port_id = f"{item.source_component_id}:{p.source_port_id}"
            
            for lbl in [l for l in sheet_labels if l.source_port_id == p.source_port_id]:
                lbl_id = get_element_id(lbl)
                lbl_node_id = f"label_node_{lbl_id}"
                # In this refactor, we still keep label nodes as top-level children of the sheet for now
                # but they are referenced by edges.
                added_labels.add(lbl_id)

            ports.append({
                "id": elk_port_id, 
                "x": px, "y": py, 
                "width": 0, "height": 0, 
                "layoutOptions": {"org.eclipse.elk.port.side": side}
            })
        
        return {
            "id": item.source_component_id, 
            "width": body_w, "height": body_h, 
            "ports": ports, 
            "layoutOptions": {"org.eclipse.elk.portConstraints": "FIXED_POS"}
        }, edges

    def _build_elk_box_node(self, cs: SourceGroup, sheet_id: str, sheet_labels, added_labels, generated) -> Tuple[ElkNode, List[Dict[str, Any]]]:
        bid = f"box_{cs.source_group_id}"
        pins = [e for e in generated if isinstance(e, SchematicHierarchicalPin) and e.schematic_box_id == bid]
        edges = []
        
        west_pins = [p for i, p in enumerate(pins) if i < (len(pins) + 1) // 2]
        east_pins = [p for i, p in enumerate(pins) if i >= (len(pins) + 1) // 2]
        
        max_w_west = max((len(p.text) for p in west_pins), default=0)
        max_w_east = max((len(p.text) for p in east_pins), default=0)
        inner_bw = max(ElkSizingConfig.MIN_BOX_W, (max_w_west + max_w_east) * 10 + ElkSizingConfig.BOX_PADDING)
        inner_bh = max(ElkSizingConfig.MIN_BOX_H, max(len(west_pins), len(east_pins)) * ElkSizingConfig.PIN_SPACING + 50)
        
        inner_ports = []
        
        for i, p in enumerate(west_pins):
            py = (i + 1) * ElkSizingConfig.PIN_SPACING
            elk_port_id = f"{bid}:{p.schematic_hierarchical_pin_id}"
            inner_ports.append({"id": elk_port_id, "x": 0, "y": py, "width": 0, "height": 0, "layoutOptions": {"org.eclipse.elk.port.side": "WEST"}})
            for lbl in [l for l in sheet_labels if l.schematic_hierarchical_pin_id == p.schematic_hierarchical_pin_id]:
                added_labels.add(get_element_id(lbl))

        for i, p in enumerate(east_pins):
            py = (i + 1) * ElkSizingConfig.PIN_SPACING
            elk_port_id = f"{bid}:{p.schematic_hierarchical_pin_id}"
            inner_ports.append({"id": elk_port_id, "x": inner_bw, "y": py, "width": 0, "height": 0, "layoutOptions": {"org.eclipse.elk.port.side": "EAST"}})
            for lbl in [l for l in sheet_labels if l.schematic_hierarchical_pin_id == p.schematic_hierarchical_pin_id]:
                added_labels.add(get_element_id(lbl))

        if sheet_id != "root":
            return {"id": bid, "width": inner_bw, "height": inner_bh, "ports": inner_ports, "layoutOptions": {"org.eclipse.elk.portConstraints": "FIXED_POS"}}, edges
        else:
            return {
                "id": bid,
                "children": [
                    {"id": f"text_name_{bid}", "width": len(cs.name or cs.source_group_id) * 10 + 60, "height": 40},
                    {"id": f"inner_body_{bid}", "width": inner_bw, "height": inner_bh, "ports": inner_ports, "layoutOptions": {"org.eclipse.elk.portConstraints": "FIXED_POS"}},
                    {"id": f"text_file_{bid}", "width": len(f"File: {cs.source_group_id}.kicad_sch") * 8 + 60, "height": 40}
                ],
                "edges": [
                    {"id": f"edge_v1_{bid}", "sources": [f"text_name_{bid}"], "targets": [f"inner_body_{bid}"]},
                    {"id": f"edge_v2_{bid}", "sources": [f"inner_body_{bid}"], "targets": [f"text_file_{bid}"]}
                ],
                "layoutOptions": {
                    "org.eclipse.elk.algorithm": "layered",
                    "org.eclipse.elk.direction": "DOWN", 
                    "org.eclipse.elk.spacing.nodeNode": "100", 
                    "org.eclipse.elk.padding": "[top=100,left=50,bottom=100,right=50]"
                }
            }, []

    def _build_elk_connectivity_edges(self, connectivity, components, child_sheets, ports_by_comp, generated) -> List[Dict[str, Any]]:
        edges = []
        port_to_elk_id = {}
        for item in components:
            for p in ports_by_comp[item.source_component_id]:
                port_to_elk_id[p.source_port_id] = f"{item.source_component_id}:{p.source_port_id}"
        for cs in child_sheets:
            bid = f"box_{cs.source_group_id}"
            box_pins = [e for e in generated if isinstance(e, SchematicHierarchicalPin) and e.schematic_box_id == bid]
            for p in box_pins:
                port_to_elk_id[p.schematic_hierarchical_pin_id] = f"{bid}:{p.schematic_hierarchical_pin_id}"

        for conn in connectivity:
            sip = conn["ports"]
            if not sip: continue
            if not conn["is_inter_group"] and not conn["is_inter_sheet"]:
                src_elk_port = port_to_elk_id.get(sip[0])
                for target_port_id in sip[1:]: 
                    tgt_elk_port = port_to_elk_id.get(target_port_id)
                    if src_elk_port and tgt_elk_port:
                        edges.append({"id": f"e_{conn['trace_id']}_{target_port_id}", "sources": [src_elk_port], "targets": [tgt_elk_port]})
            if conn["is_inter_sheet"] and conn["hpin_id"]:
                src_elk_port = port_to_elk_id.get(sip[0])
                tgt_elk_port = port_to_elk_id.get(conn["hpin_id"])
                if src_elk_port and tgt_elk_port:
                    edges.append({"id": f"e_to_hpin_{conn['trace_id']}", "sources": [src_elk_port], "targets": [tgt_elk_port]})
        return edges

    def _parse_sheet_layout(self, sheet_id, data, components, ports_by_comp, subgroups, child_sheets, generated, symbol_map):
        results = []
        def snap(v): return float(round(v / KICAD_GRID_UNITS) * KICAD_GRID_UNITS)

        # 1. Process Nodes
        for node in data.get("children", []):
            cid = node["id"]
            if cid.startswith("fixed_"): continue

            nx, ny = snap(node["x"]), snap(node["y"])

            if cid.startswith("label_node_"):
                lbl_id = cid.replace("label_node_", "")
                lbl = next((e for e in generated if get_element_id(e) == lbl_id), None)
                if lbl:
                    lw, lh = snap(node.get("width", 0)), snap(node.get("height", 0))
                    lbl.center = Point(x=snap(nx + lw / 2), y=snap(ny + lh / 2))
                continue

            if cid.startswith("box_"):
                inner = next((c for c in node.get("children", []) if c["id"].startswith("inner_body_")), None)
                if inner:
                    bx = snap(nx + inner["x"])
                    by = snap(ny + inner["y"])
                    bw, bh = snap(inner["width"]), snap(inner["height"])
                    name_node = next((c for c in node.get("children", []) if c["id"].startswith("text_name_")), None)
                    file_node = next((c for c in node.get("children", []) if c["id"].startswith("text_file_")), None)
                    name_off = Point(x=snap(name_node["x"] - inner["x"]), y=snap(name_node["y"] - inner["y"])) if name_node else Point(x=0, y=-20)
                    file_off = Point(x=snap(file_node["x"] - inner["x"]), y=snap(file_node["y"] - inner["y"])) if file_node else Point(x=0, y=bh + 20)
                    results.append(SchematicBox(schematic_box_id=cid, sheet_id=sheet_id, x=bx, y=by, width=bw, height=bh, is_hierarchical_sheet=True, name_offset=name_off, file_offset=file_off))
                    
                    # Handle Port Labels inside the nested body
                    for p_data in inner.get("ports", []):
                        actual_id = p_data["id"].split(":", 1)[1] if ":" in p_data["id"] else p_data["id"]
                        hp = next((e for e in generated if isinstance(e, SchematicHierarchicalPin) and e.schematic_hierarchical_pin_id == actual_id), None)
                        if hp:
                            hp.center = Point(x=snap(bx + p_data["x"]), y=snap(by + p_data["y"]))
                else:
                    bw, bh = snap(node["width"]), snap(node["height"])
                    results.append(SchematicBox(schematic_box_id=cid, sheet_id=sheet_id, x=nx, y=ny, width=bw, height=bh, is_hierarchical_sheet=True))
                    for p_data in node.get("ports", []):
                        actual_id = p_data["id"].split(":", 1)[1] if ":" in p_data["id"] else p_data["id"]
                        hp = next((e for e in generated if isinstance(e, SchematicHierarchicalPin) and e.schematic_hierarchical_pin_id == actual_id), None)
                        if hp:
                            hp.center = Point(x=snap(nx + p_data["x"]), y=snap(ny + p_data["y"]))
                continue

            comp_id = cid
            comp = next((c for c in components if c.source_component_id == comp_id), None)
            if comp:
                sym = symbol_map.get(comp.symbol_id)
                off = sym.bounding_box_min if sym else Point(x=0, y=0)
                results.append(SchematicComponent(schematic_component_id=f"sch_{comp_id}", sheet_id=sheet_id, source_component_id=comp_id, center=Point(x=nx - off.x, y=ny - off.y)))

                # Generate SchematicPort elements and handle Port Labels
                comp_ports = ports_by_comp[comp_id]
                symbol_pins = {p.number: p for p in sym.pins} if sym else {}

                for p in comp_ports:
                    pi = symbol_pins.get(str(p.pin_number)) or next((pin for pin in symbol_pins.values() if pin.name == p.name), None)
                    if pi:
                        px, py = nx + (pi.grid_offset.x - sym.bounding_box_min.x), ny + (pi.grid_offset.y - sym.bounding_box_min.y)
                    else:
                        px, py = nx, ny

                    results.append(SchematicPort(
                        schematic_port_id=f"port_{get_element_id(p)}",
                        source_port_id=p.source_port_id,
                        sheet_id=sheet_id,
                        center=Point(x=snap(px), y=snap(py))
                    ))
        # 2. Process Edges (Wires)
        for edge in data.get("edges", []):
            eid = edge["id"]
            
            source_tid = None
            if eid.startswith("e_label_"):
                # Position the label at the endpoint of the edge
                lbl_id = eid.replace("e_label_", "")
                lbl = next((e for e in generated if get_element_id(e) == lbl_id), None)
                if lbl:
                    sec = edge.get("sections", [{}])[0]
                    if "endPoint" in sec:
                        ep = sec["endPoint"]
                        lbl.center = Point(x=snap(ep["x"]), y=snap(ep["y"]))
                        
                        # Determine anchor side from last segment direction
                        pts = [sec["startPoint"]] + sec.get("bendPoints", []) + [sec["endPoint"]]
                        if len(pts) >= 2:
                            p2 = pts[-1]
                            p1 = pts[-2]
                            dx, dy = p2["x"] - p1["x"], p2["y"] - p1["y"]
                            if abs(dx) > abs(dy): lbl.anchor_side = "left" if dx > 0 else "right"
                            else: lbl.anchor_side = "top" if dy > 0 else "bottom"
                # Continue to draw the wire to the label
                source_tid = getattr(lbl, "source_net_id", "label_connection") if lbl else "label_connection"
            elif eid.startswith("e_"):
                parts = eid.split("_")
                if parts[1] == "to" and parts[2] == "hpin":
                    source_tid = parts[3]
                else:
                    source_tid = parts[1]
            for sec in edge.get("sections", []):
                pts = [Point(x=snap(sec["startPoint"]["x"]), y=snap(sec["startPoint"]["y"]))]
                pts.extend([Point(x=snap(bp["x"]), y=snap(bp["y"])) for bp in sec.get("bendPoints", [])])
                pts.append(Point(x=snap(sec["endPoint"]["x"]), y=snap(sec["endPoint"]["y"])))
                el = []
                for i in range(len(pts)-1):
                    if pts[i].x != pts[i+1].x or pts[i].y != pts[i+1].y: 
                        el.append(SchematicTraceEdge.model_validate({"from": pts[i], "to": pts[i+1]}))
                if el: 
                    results.append(SchematicTrace(
                        schematic_trace_id=f"sch_{eid}", 
                        source_trace_id=source_tid,
                        sheet_id=sheet_id, 
                        edges=el
                    ))
        return results

    def _snap_labels(self, labels, comp_origins, source_ports, symbols, source_components, all_positioned, sheet_id):
        """No longer used as labels are positioned via ELK edge endpoints."""
        pass


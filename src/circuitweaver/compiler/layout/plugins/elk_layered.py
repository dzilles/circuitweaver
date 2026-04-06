import logging
from typing import Any, Dict, List, Optional, Tuple
from circuitweaver.types.circuit_json import (
    CircuitElement, Point, SchematicBox, SchematicComponent, 
    SchematicHierarchicalPin, SchematicPort, SchematicTrace, 
    SchematicTraceEdge, SourceComponent, SourceGroup, SourcePort, 
    SchematicNetLabel, SchematicHierarchicalLabel, SchematicNoConnect,
    get_element_id
)
from .base import LayoutPlugin
from ..registry import LayoutContext
from ..models import LayoutNode, LayoutPort, LayoutEdge

logger = logging.getLogger(__name__)

class ElkSizingConfig:
    PIN_SPACING = 20
    MIN_BOX_W = 250
    MIN_BOX_H = 100

class ElkLayeredPlugin(LayoutPlugin):
    """Main plugin for layered auto-layout of components and hierarchical boxes."""

    def build(self, context: LayoutContext) -> None:
        source_components = [e for e in context.elements if isinstance(e, SourceComponent)]
        source_groups = [e for e in context.elements if isinstance(e, SourceGroup)]
        
        # 1. Components
        for comp in source_components:
            self._add_component_node(comp, context)
            
        # 2. Hierarchical Boxes
        for group in source_groups:
            if group.is_subcircuit:
                self._add_box_node(group, context)

        # 3. Connectivity (Traces)
        self._build_connectivity(context)

    def _add_component_node(self, comp: SourceComponent, context: LayoutContext):
        symbol = context.symbol_map.get(comp.symbol_id)
        width, height = (symbol.width, symbol.height) if symbol else (40, 40)
        
        ports = []
        if symbol:
            for p_info in symbol.pins:
                px = p_info.grid_offset.x - symbol.bounding_box_min.x
                py = p_info.grid_offset.y - symbol.bounding_box_min.y
                
                # Side mapping: match KiCad direction to ELK side
                # KiCad 'left' (180 deg) points left -> WEST
                # KiCad 'right' (0 deg) points right -> EAST
                # KiCad 'up' (90 deg) points up -> NORTH
                # KiCad 'down' (270 deg) points down -> SOUTH
                side = {
                    "left": "WEST", 
                    "right": "EAST", 
                    "up": "NORTH", 
                    "down": "SOUTH"
                }.get(p_info.direction, "WEST")
                
                port_id = f"{comp.source_component_id}:{p_info.number}"
                ports.append(LayoutPort(
                    id=port_id, x=px, y=py, 
                    layoutOptions={"org.eclipse.elk.port.side": side}
                ))
                
                sp = next((p for p in context.elements if isinstance(p, SourcePort) and p.source_component_id == comp.source_component_id and str(p.pin_number) == str(p_info.number)), None)
                if sp:
                    context.registry.register_port(sp, port_id)

        node = LayoutNode(
            id=comp.source_component_id, width=width, height=height, 
            ports=ports, layoutOptions={"org.eclipse.elk.portConstraints": "FIXED_POS"}
        )
        context.root_node.children.append(node)
        context.registry.register_node(comp, comp.source_component_id)

    def _add_box_node(self, group: SourceGroup, context: LayoutContext):
        bid = f"box_{group.source_group_id}"
        pins = [e for e in context.elements if isinstance(e, SchematicHierarchicalPin) and e.schematic_box_id == bid]
        
        # Split pins between West and East sides
        west_pins = [p for i, p in enumerate(pins) if i < (len(pins) + 1) // 2]
        east_pins = [p for i, p in enumerate(pins) if i >= (len(pins) + 1) // 2]
        
        max_w_west = max((len(p.text) for p in west_pins), default=0)
        max_w_east = max((len(p.text) for p in east_pins), default=0)
        
        bw = max(ElkSizingConfig.MIN_BOX_W, (max_w_west + max_w_east) * 8 + 100)
        bh = max(ElkSizingConfig.MIN_BOX_H, max(len(west_pins), len(east_pins)) * ElkSizingConfig.PIN_SPACING + 50)
        
        ports = []
        for i, p in enumerate(west_pins):
            py = (i + 1) * ElkSizingConfig.PIN_SPACING
            port_id = f"{bid}:{p.schematic_hierarchical_pin_id}"
            ports.append(LayoutPort(id=port_id, x=0, y=py, layoutOptions={"org.eclipse.elk.port.side": "WEST"}))
            context.registry.register_port(p, port_id)

        for i, p in enumerate(east_pins):
            py = (i + 1) * ElkSizingConfig.PIN_SPACING
            port_id = f"{bid}:{p.schematic_hierarchical_pin_id}"
            ports.append(LayoutPort(id=port_id, x=bw, y=py, layoutOptions={"org.eclipse.elk.port.side": "EAST"}))
            context.registry.register_port(p, port_id)

        inner_body = LayoutNode(
            id=f"inner_body_{bid}", width=bw, height=bh, ports=ports,
            layoutOptions={"org.eclipse.elk.portConstraints": "FIXED_POS"}
        )
        
        name_text = group.name or group.source_group_id
        file_text = f"File: {group.source_group_id.replace('box_', '')}.kicad_sch"

        node = LayoutNode(
            id=bid,
            children=[
                LayoutNode(id=f"text_name_{bid}", width=len(name_text) * 10 + 60, height=40),
                inner_body,
                LayoutNode(id=f"text_file_{bid}", width=len(file_text) * 8 + 60, height=40)
            ],
            edges=[
                LayoutEdge(id=f"edge_v1_{bid}", sources=[f"text_name_{bid}"], targets=[f"inner_body_{bid}"]),
                LayoutEdge(id=f"edge_v2_{bid}", sources=[f"inner_body_{bid}"], targets=[f"text_file_{bid}"])
            ],
            layoutOptions={
                "org.eclipse.elk.algorithm": "layered",
                "org.eclipse.elk.direction": "DOWN",
                "org.eclipse.elk.spacing.nodeNode": "100",
                "org.eclipse.elk.padding": "[top=100,left=50,bottom=100,right=50]"
            }
        )
        context.root_node.children.append(node)
        context.registry.register_node(group, bid)

    def _build_connectivity(self, context: LayoutContext):
        sheet_conn = context.sheet_connectivity.get(context.sheet_id, [])
        for conn in sheet_conn:
            sip = conn["ports"]
            if not sip: continue
            
            src_elk_id = context.registry.element_to_port.get(sip[0])
            if not src_elk_id: continue
            
            if not conn.get("is_inter_group") and not conn.get("is_inter_sheet"):
                for target_port_id in sip[1:]:
                    tgt_elk_id = context.registry.element_to_port.get(target_port_id)
                    if tgt_elk_id:
                        context.root_node.edges.append(LayoutEdge(
                            id=f"e_{conn['trace_id']}_{target_port_id}",
                            sources=[src_elk_id], targets=[tgt_elk_id]
                        ))
            
            if conn.get("is_inter_sheet") and conn.get("hpin_id"):
                h_elk_id = context.registry.element_to_port.get(conn["hpin_id"])
                if h_elk_id:
                    context.root_node.edges.append(LayoutEdge(
                        id=f"e_to_hpin_{conn['trace_id']}",
                        sources=[src_elk_id], targets=[h_elk_id]
                    ))

    def apply(self, context: LayoutContext, results: Dict[str, Any]) -> List[CircuitElement]:
        final_elements: List[CircuitElement] = []
        
        # KiCad standard grid is 50 mils = 10 units (1 unit = 0.127mm)
        def snap(v): return float(round(v / 10.0) * 10.0)

        def parse_nodes_recursive(node_data: Dict[str, Any], px=0, py=0):
            nid = node_data["id"]
            nx, ny = snap(node_data["x"] + px), snap(node_data["y"] + py)
            
            element = context.registry.get_element_by_layout_id(nid)
            
            if isinstance(element, SourceComponent):
                sym = context.symbol_map.get(element.symbol_id)
                off = sym.bounding_box_min if sym else Point(x=0, y=0)
                cx, cy = snap(nx - off.x), snap(ny - off.y)
                final_elements.append(SchematicComponent(
                    schematic_component_id=f"sch_{nid}", 
                    sheet_id=context.sheet_id, 
                    source_component_id=nid, 
                    center=Point(x=cx, y=cy)
                ))
                
                comp_ports = [e for e in context.elements if isinstance(e, SourcePort) and e.source_component_id == nid]
                symbol_pins = {p.number: p for p in sym.pins} if sym else {}
                for p in comp_ports:
                    pi = symbol_pins.get(str(p.pin_number)) or next((pin for pin in symbol_pins.values() if pin.name == p.name), None)
                    if pi:
                        px_port = snap(nx + (pi.grid_offset.x - sym.bounding_box_min.x))
                        py_port = snap(ny + (pi.grid_offset.y - sym.bounding_box_min.y))
                        final_elements.append(SchematicPort(
                            schematic_port_id=f"port_{get_element_id(p)}", 
                            source_port_id=p.source_port_id, 
                            sheet_id=context.sheet_id, 
                            center=Point(x=px_port, y=py_port)
                        ))
                
                for child in node_data.get("children", []):
                    parse_nodes_recursive(child, nx, ny)

            elif isinstance(element, SourceGroup):
                inner = next((c for c in node_data.get("children", []) if c["id"].startswith("inner_body_")), None)
                if inner:
                    bx, by = snap(nx + inner["x"]), snap(ny + inner["y"])
                    bw, bh = snap(inner["width"]), snap(inner["height"])
                    
                    for p_data in inner.get("ports", []):
                        actual_id = p_data["id"].split(":", 1)[1] if ":" in p_data["id"] else p_data["id"]
                        hp = next((e for e in context.elements if isinstance(e, SchematicHierarchicalPin) and e.schematic_hierarchical_pin_id == actual_id), None)
                        if hp:
                            hp.center = Point(x=snap(bx + p_data["x"]), y=snap(by + p_data["y"]))
                    
                    final_elements.append(SchematicBox(
                        schematic_box_id=nid, sheet_id=context.sheet_id, 
                        x=bx, y=by, width=bw, height=bh, 
                        is_hierarchical_sheet=True
                    ))
                    
                    # Recurse into children of inner body and parent box, but skip inner_body itself to avoid double offset
                    for child in node_data.get("children", []):
                        if not child["id"].startswith("inner_body_"):
                            parse_nodes_recursive(child, nx, ny)
                    for child in inner.get("children", []):
                        parse_nodes_recursive(child, bx, by)
                else:
                    # Fallback
                    bx, by = nx, ny
                    bw, bh = snap(node_data["width"]), snap(node_data["height"])
                    final_elements.append(SchematicBox(
                        schematic_box_id=nid, sheet_id=context.sheet_id, 
                        x=bx, y=by, width=bw, height=bh, 
                        is_hierarchical_sheet=True
                    ))
                    for child in node_data.get("children", []):
                        parse_nodes_recursive(child, nx, ny)

            elif isinstance(element, (SchematicNetLabel, SchematicHierarchicalLabel)):
                element.center = Point(x=nx, y=ny)

            elif isinstance(element, SchematicNoConnect):
                element.position = Point(x=nx, y=ny)

            else:
                for child in node_data.get("children", []):
                    parse_nodes_recursive(child, nx, ny)

        for child in results.get("children", []):
            parse_nodes_recursive(child)
            
        self._parse_edges_recursive(results, 0, 0, context, final_elements, snap)
        return final_elements

    def _parse_edges_recursive(self, node_data: Dict[str, Any], px: float, py: float, context: LayoutContext, final_elements: List[CircuitElement], snap):
        nx, ny = snap(node_data["x"] + px), snap(node_data["y"] + py)

        for edge in node_data.get("edges", []):
            eid = edge["id"]
            if eid.startswith("e_v"): continue
            
            source_tid = None
            if eid.startswith("e_label_"): 
                lbl_id = eid.replace("e_label_", "")
                lbl = context.registry.get_element_by_layout_id(lbl_id)
                if isinstance(lbl, (SchematicNetLabel, SchematicHierarchicalLabel)):
                    sec = edge.get("sections", [{}])[0]
                    if "endPoint" in sec:
                        ep = sec["endPoint"]
                        lbl.center = Point(x=snap(ep["x"] + nx), y=snap(ep["y"] + ny))
                        pts = [sec["startPoint"]] + sec.get("bendPoints", []) + [sec["endPoint"]]
                        if len(pts) >= 2:
                            p2, p1 = pts[-1], pts[-2]
                            dx, dy = p2["x"] - p1["x"], p2["y"] - p1["y"]
                            if abs(dx) > abs(dy): lbl.anchor_side = "left" if dx > 0 else "right"
                            else: lbl.anchor_side = "top" if dy > 0 else "bottom"
                source_tid = getattr(lbl, "source_net_id", None) if lbl else None
            elif eid.startswith("e_nc_"): continue
            elif eid.startswith("e_"):
                parts = eid.split("_")
                if len(parts) >= 4 and parts[1] == "to" and parts[2] == "hpin": 
                    source_tid = parts[3]
                else: 
                    source_tid = parts[1]
            
            for sec in edge.get("sections", []):
                pts = [Point(x=snap(sec["startPoint"]["x"] + nx), y=snap(sec["startPoint"]["y"] + ny))]
                pts.extend([Point(x=snap(bp["x"] + nx), y=snap(bp["y"] + ny)) for bp in sec.get("bendPoints", [])])
                pts.append(Point(x=snap(sec["endPoint"]["x"] + nx), y=snap(sec["endPoint"]["y"] + ny)))
                
                trace_edges = []
                for i in range(len(pts)-1):
                    if pts[i].x != pts[i+1].x or pts[i].y != pts[i+1].y: 
                        trace_edges.append(SchematicTraceEdge.model_validate({"from": pts[i], "to": pts[i+1]}))
                
                if trace_edges:
                    final_elements.append(SchematicTrace(
                        schematic_trace_id=f"sch_{eid}_{id(sec)}", 
                        source_trace_id=source_tid, 
                        sheet_id=context.sheet_id, 
                        edges=trace_edges
                    ))

        for child in node_data.get("children", []):
            self._parse_edges_recursive(child, node_data["x"] + px, node_data["y"] + py, context, final_elements, snap)

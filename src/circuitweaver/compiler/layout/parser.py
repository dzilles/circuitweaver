import logging
from typing import Any, Dict, List, Optional

from circuitweaver.library.pinout import SymbolInfo
from circuitweaver.types.circuit_json import (
    CircuitElement,
    Point,
    SchematicBox,
    SchematicComponent,
    SchematicHierarchicalPin,
    SchematicNoConnect,
    SchematicPort,
    SchematicTrace,
    SchematicTraceEdge,
    SourceComponent,
    SourcePort,
    get_element_id,
)

logger = logging.getLogger(__name__)

# KiCad standard grid is 50mils (10 units in our system)
KICAD_GRID_UNITS = 10


class ElkGraphParser:
    """
    Parses ELK JSON layout results back into Circuit JSON schematic elements.
    """

    def parse_sheet_layout(
        self,
        sheet_id: str,
        layout_data: Dict[str, Any],
        components: List[SourceComponent],
        ports_by_comp: Dict[str, List[SourcePort]],
        generated_elements: List[CircuitElement],
        symbol_map: Dict[str, SymbolInfo],
    ) -> List[CircuitElement]:
        """
        Main entry point for parsing ELK layout data.
        """
        results: List[CircuitElement] = []

        # 1. Process Nodes recursively
        for node in layout_data.get("children", []):
            self._parse_node_recursive(
                node, 0, 0, sheet_id, results, components, ports_by_comp, generated_elements, symbol_map
            )

        # 2. Process Edges (Wires)
        for edge in layout_data.get("edges", []):
            self._parse_edge(edge, sheet_id, results, generated_elements)

        return results

    def _parse_node_recursive(
        self,
        node: Dict[str, Any],
        parent_x: float,
        parent_y: float,
        sheet_id: str,
        results: List[CircuitElement],
        components: List[SourceComponent],
        ports_by_comp: Dict[str, List[SourcePort]],
        generated_elements: List[CircuitElement],
        symbol_map: Dict[str, SymbolInfo],
    ) -> None:
        """
        Dispatcher method that routes node parsing based on ID prefixes.
        """
        node_id: str = node["id"]
        abs_x = node["x"] + parent_x
        abs_y = node["y"] + parent_y

        if node_id.startswith("label_node_"):
            self._parse_label_node(node, abs_x, abs_y, generated_elements)
        elif node_id.startswith("box_"):
            self._parse_box_node(
                node, abs_x, abs_y, sheet_id, results, generated_elements
            )
        else:
            # Check if it's a component node
            comp = next((c for c in components if c.source_component_id == node_id), None)
            if comp:
                self._parse_component_node(
                    node, abs_x, abs_y, sheet_id, results, comp, ports_by_comp, symbol_map
                )

        # Recurse for children (e.g., inner elements of a hierarchical box)
        for child in node.get("children", []):
            self._parse_node_recursive(
                child, abs_x, abs_y, sheet_id, results, components, ports_by_comp, generated_elements, symbol_map
            )

    def _parse_label_node(
        self, node: Dict[str, Any], abs_x: float, abs_y: float, generated_elements: List[CircuitElement]
    ) -> None:
        # We no longer position labels based on node centers. 
        # Labels are now positioned based on the wires (edges) that connect to them.
        pass

    def _parse_box_node(
        self,
        node: Dict[str, Any],
        abs_x: float,
        abs_y: float,
        sheet_id: str,
        results: List[CircuitElement],
        generated_elements: List[CircuitElement],
    ) -> None:
        cid: str = node["id"]
        inner = next((c for c in node.get("children", []) if c["id"].startswith("inner_body_")), None)
        
        if inner:
            # Root sheet layout with nested inner_body
            bx = abs_x + inner["x"]
            by = abs_y + inner["y"]
            bw, bh = inner["width"], inner["height"]
        else:
            # Simple box layout
            bx, by = abs_x, abs_y
            bw, bh = node["width"], node["height"]
            
        results.append(SchematicBox(
            schematic_box_id=cid, sheet_id=sheet_id, 
            x=bx, y=by, width=bw, height=bh, 
            is_hierarchical_sheet=True
        ))

        # Position hierarchical pins (ports)
        # Ports may be on the main node or the inner_body child
        ports_source = inner if inner else node
        port_abs_x = abs_x + (inner["x"] if inner else 0)
        port_abs_y = abs_y + (inner["y"] if inner else 0)

        for p_data in ports_source.get("ports", []):
            # The port ID in ELK might be "parent:pin_id" or just "pin_id"
            pid = p_data["id"].split(":")[-1]
            hp = next((
                e for e in generated_elements 
                if isinstance(e, SchematicHierarchicalPin) 
                and e.schematic_hierarchical_pin_id == pid
            ), None)
            if hp and hp.schematic_box_id == cid:
                hp.center = Point(x=(port_abs_x + p_data["x"]), y=(port_abs_y + p_data["y"]))

    def _parse_component_node(
        self,
        node: Dict[str, Any],
        abs_x: float,
        abs_y: float,
        sheet_id: str,
        results: List[CircuitElement],
        comp: SourceComponent,
        ports_by_comp: Dict[str, List[SourcePort]],
        symbol_map: Dict[str, SymbolInfo],
    ) -> None:
        cid: str = node["id"]
        sym = symbol_map.get(comp.symbol_id)
        off = sym.bounding_box_min if sym else Point(x=0, y=0)
        
        # ELK node top-left to KiCad symbol origin translation
        center_x = abs_x - off.x
        center_y = abs_y - off.y
        
        results.append(SchematicComponent(
            schematic_component_id=f"sch_{cid}", 
            sheet_id=sheet_id, 
            source_component_id=cid, 
            center=Point(x=center_x, y=center_y)
        ))
        
        comp_ports = ports_by_comp[cid]
        symbol_pins = {p.number: p for p in sym.pins} if sym else {}

        for p in comp_ports:
            pi = symbol_pins.get(str(p.pin_number)) or next((pin for pin in symbol_pins.values() if pin.name == p.name), None)
            px, py = (center_x + pi.grid_offset.x, center_y + pi.grid_offset.y) if pi else (center_x, center_y)
            results.append(SchematicPort(
                schematic_port_id=f"port_{get_element_id(p)}", 
                source_port_id=p.source_port_id, 
                sheet_id=sheet_id, 
                center=Point(x=px, y=py)
            ))

    def _parse_edge(
        self, 
        edge: Dict[str, Any], 
        sheet_id: str, 
        results: List[CircuitElement], 
        generated_elements: List[CircuitElement]
    ) -> None:
        eid: str = edge["id"]
        source_tid: Optional[str] = None
        
        if eid.startswith("e_label_"):
            self._process_label_edge(edge, results, generated_elements)
            return
        elif eid.startswith("e_nc_"):
            self._process_nc_edge(edge, results, generated_elements)
            return
        elif eid.startswith("e_"):
            parts = eid.split("_")
            if len(parts) >= 4 and parts[1] == "to" and parts[2] == "hpin": 
                source_tid = parts[3]
            else: 
                source_tid = parts[1]
        
        for sec in edge.get("sections", []):
            pts = [Point(x=sec["startPoint"]["x"], y=sec["startPoint"]["y"])]
            pts.extend([Point(x=bp["x"], y=bp["y"]) for bp in sec.get("bendPoints", [])])
            pts.append(Point(x=sec["endPoint"]["x"], y=sec["endPoint"]["y"]))
            
            trace_edges = []
            for i in range(len(pts)-1):
                if pts[i].x != pts[i+1].x or pts[i].y != pts[i+1].y: 
                    trace_edges.append(SchematicTraceEdge.model_validate({"from": pts[i], "to": pts[i+1]}))
            
            if trace_edges: 
                results.append(SchematicTrace(
                    schematic_trace_id=f"sch_{eid}", 
                    source_trace_id=source_tid, 
                    sheet_id=sheet_id, 
                    edges=trace_edges
                ))

    def _process_label_edge(
        self, 
        edge: Dict[str, Any], 
        results: List[CircuitElement], 
        generated_elements: List[CircuitElement]
    ) -> None:
        lbl_id = edge["id"].replace("e_label_", "")
        lbl = next((e for e in generated_elements if get_element_id(e) == lbl_id), None)
        if not lbl:
            return

        for sec in edge.get("sections", []):
            # Extract the full path from ELK
            pts = [Point(x=sec["startPoint"]["x"], y=sec["startPoint"]["y"])]
            pts.extend([Point(x=bp["x"], y=bp["y"]) for bp in sec.get("bendPoints", [])])
            pts.append(Point(x=sec["endPoint"]["x"], y=sec["endPoint"]["y"]))
            
            # Position the label EXACTLY at the end of the wire
            lbl.center = pts[-1]
            
            trace_edges = []
            for i in range(len(pts)-1):
                if pts[i].x != pts[i+1].x or pts[i].y != pts[i+1].y: 
                    trace_edges.append(SchematicTraceEdge.model_validate({"from": pts[i], "to": pts[i+1]}))
            
            if trace_edges:
                # Add the wire to the results so it's drawn in KiCad
                results.append(SchematicTrace(
                    schematic_trace_id=f"sch_{edge['id']}", 
                    source_trace_id=getattr(lbl, 'source_trace_id', None) or lbl.source_net_id, 
                    sheet_id=lbl.sheet_id, 
                    edges=trace_edges
                ))
                
                # Determine anchor side based on the approach angle of the last segment
                p2, p1 = pts[-1], pts[-2]
                dx, dy = p2.x - p1.x, p2.y - p1.y
                if abs(dx) > abs(dy): 
                    lbl.anchor_side = "left" if dx > 0 else "right"
                else: 
                    lbl.anchor_side = "top" if dy > 0 else "bottom"

    def _process_nc_edge(
        self, 
        edge: Dict[str, Any], 
        results: List[CircuitElement], 
        generated_elements: List[CircuitElement]
    ) -> None:
        nc_id = edge["id"].replace("e_nc_", "")
        nc = next((e for e in generated_elements if isinstance(e, SchematicNoConnect) and e.schematic_no_connect_id == nc_id), None)
        if nc:
            # Position the NC flag exactly at the port (the start of the edge)
            sec = edge.get("sections", [{}])[0]
            if "startPoint" in sec:
                sp = sec["startPoint"]
                nc.position = Point(x=sp["x"], y=sp["y"])
                # We do NOT add a SchematicTrace for NC flags.

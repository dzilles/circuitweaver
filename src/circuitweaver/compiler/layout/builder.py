import logging
from typing import Any, Dict, List, Set, Tuple, TypedDict

from circuitweaver.library.pinout import SymbolInfo
from circuitweaver.types.circuit_json import (
    CircuitElement,
    SchematicHierarchicalPin,
    SchematicNetLabel,
    SchematicHierarchicalLabel,
    SchematicNoConnect,
    SourceComponent,
    SourceGroup,
    SourcePort,
    get_element_id,
)

logger = logging.getLogger(__name__)


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
    x: float
    y: float


class ElkGraphBuilder:
    """
    Translates Circuit JSON elements into an ELK JSON graph representation.
    """

    def build_sheet_graph(
        self,
        sheet_id: str,
        components: List[SourceComponent],
        child_sheets: List[SourceGroup],
        ports_by_comp: Dict[str, List[SourcePort]],
        connectivity: List[Dict[str, Any]],
        generated_elements: List[CircuitElement],
        symbol_map: Dict[str, SymbolInfo],
    ) -> ElkNode:
        """
        Constructs the ELK graph for a specific schematic sheet.
        """
        nodes: List[ElkNode] = []
        edges: List[Dict[str, Any]] = []
        
        sheet_labels = [
            e for e in generated_elements 
            if isinstance(e, (SchematicNetLabel, SchematicHierarchicalLabel)) 
            and e.sheet_id == sheet_id
        ]
        sheet_nc_flags = [
            e for e in generated_elements 
            if isinstance(e, SchematicNoConnect) 
            and e.sheet_id == sheet_id
        ]
        added_labels: Set[str] = set()

        # 1. Component Nodes
        for comp in components:
            node, comp_edges, label_nodes = self._build_component_node(
                comp, ports_by_comp[comp.source_component_id], sheet_labels, sheet_nc_flags, added_labels, symbol_map
            )
            nodes.append(node)
            edges.extend(comp_edges)
            nodes.extend(label_nodes)
        
        # 2. Child Sheet Box Nodes
        for group in child_sheets:
            node, box_edges, label_nodes = self._build_box_node(
                group, sheet_id, sheet_labels, added_labels, generated_elements
            )
            nodes.append(node)
            edges.extend(box_edges)
            nodes.extend(label_nodes)

        # 3. Connectivity Edges
        edges.extend(self._build_connectivity_edges(
            connectivity, components, child_sheets, ports_by_comp, generated_elements, sheet_id
        ))
            
        options = {
            "org.eclipse.elk.algorithm": "layered",
            "org.eclipse.elk.spacing.nodeNode": "40" if sheet_id != "root" else "100",
            "org.eclipse.elk.layered.spacing.nodeNodeBetweenLayers": "60" if sheet_id != "root" else "150",
            "org.eclipse.elk.layered.nodePlacement.strategy": "BRANDES_KOEPF",
            "org.eclipse.elk.aspectRatio": "1.414",
            "org.eclipse.elk.padding": f"[top=200,left=200,bottom={ElkSizingConfig.TB_HEIGHT + 200},right={ElkSizingConfig.TB_WIDTH + 200}]"
        }
            
        return {"id": sheet_id, "children": nodes, "edges": edges, "layoutOptions": options}

    def _build_component_node(
        self, 
        item: SourceComponent, 
        comp_ports: List[SourcePort], 
        sheet_labels: List[CircuitElement], 
        sheet_nc_flags: List[SchematicNoConnect],
        added_labels: Set[str], 
        symbol_map: Dict[str, SymbolInfo]
    ) -> Tuple[ElkNode, List[Dict[str, Any]], List[ElkNode]]:
        symbol = symbol_map.get(item.symbol_id)
        body_w, body_h = (symbol.width, symbol.height) if symbol else (40, 40)
        body_w, body_h = max(body_w, 10), max(body_h, 10)
        
        ports: List[ElkPort] = []
        edges: List[Dict[str, Any]] = []
        symbol_pins = {p.number: p for p in symbol.pins} if symbol else {}
        label_nodes: List[ElkNode] = []
        
        for p in comp_ports:
            pi = symbol_pins.get(str(p.pin_number)) or next((pin for pin in symbol_pins.values() if pin.name == p.name), None)
            if pi:
                px, py = (pi.grid_offset.x - symbol.bounding_box_min.x, pi.grid_offset.y - symbol.bounding_box_min.y)
                side = {"left": "EAST", "right": "WEST", "up": "SOUTH", "down": "NORTH"}.get(pi.direction, "WEST")
            else:
                px, py = 0, 0
                side = "WEST"
            
            elk_port_id = f"{item.source_component_id}:{p.source_port_id}"
            
            # Find and add labels associated with this port
            port_labels = [
                l for l in sheet_labels 
                if isinstance(l, (SchematicNetLabel, SchematicHierarchicalLabel)) 
                and getattr(l, 'source_port_id', None) == p.source_port_id
            ]
            for lbl in port_labels:
                lbl_id = get_element_id(lbl)
                lbl_node_id = f"label_node_{lbl_id}"
                label_nodes.append({
                    "id": lbl_node_id, 
                    "width": len(lbl.text) * ElkSizingConfig.CHAR_WIDTH_PX, 
                    "height": ElkSizingConfig.LABEL_HEIGHT
                })
                edges.append({
                    "id": f"e_label_{lbl_id}",
                    "sources": [elk_port_id],
                    "targets": [lbl_node_id]
                })
                added_labels.add(lbl_id)

            # Find and add no-connect flags associated with this port
            port_id = get_element_id(p)
            for nc in [n for n in sheet_nc_flags if n.schematic_port_id in (port_id, f"port_{port_id}")]:
                nc_id = nc.schematic_no_connect_id
                nc_node_id = f"nc_node_{nc_id}"
                label_nodes.append({
                    "id": nc_node_id, 
                    "width": 0, "height": 0
                })
                edges.append({
                    "id": f"e_nc_{nc_id}",
                    "sources": [elk_port_id],
                    "targets": [nc_node_id]
                })

            ports.append({
                "id": elk_port_id, 
                "x": px, "y": py, 
                "width": 0, "height": 0, 
                "layoutOptions": {"org.eclipse.elk.port.side": side}
            })
        
        node: ElkNode = {
            "id": item.source_component_id, 
            "width": body_w, "height": body_h, 
            "ports": ports, 
            "layoutOptions": {"org.eclipse.elk.portConstraints": "FIXED_POS"}
        }
        return node, edges, label_nodes

    def _build_box_node(
        self, 
        group: SourceGroup, 
        sheet_id: str, 
        sheet_labels: List[CircuitElement], 
        added_labels: Set[str], 
        generated_elements: List[CircuitElement]
    ) -> Tuple[ElkNode, List[Dict[str, Any]], List[ElkNode]]:
        bid = f"box_{group.source_group_id}"
        pins = [
            e for e in generated_elements 
            if isinstance(e, SchematicHierarchicalPin) and e.schematic_box_id == bid
        ]
        edges: List[Dict[str, Any]] = []
        
        # Distribute pins between left and right sides
        west_pins = [p for i, p in enumerate(pins) if i < (len(pins) + 1) // 2]
        east_pins = [p for i, p in enumerate(pins) if i >= (len(pins) + 1) // 2]
        
        max_w_west = max((len(p.text) for p in west_pins), default=0)
        max_w_east = max((len(p.text) for p in east_pins), default=0)
        inner_bw = max(ElkSizingConfig.MIN_BOX_W, (max_w_west + max_w_east) * 10 + ElkSizingConfig.BOX_PADDING)
        inner_bh = max(ElkSizingConfig.MIN_BOX_H, max(len(west_pins), len(east_pins)) * ElkSizingConfig.PIN_SPACING + 50)
        
        inner_ports: List[ElkPort] = []
        label_nodes: List[ElkNode] = []
        
        def process_pin(p: SchematicHierarchicalPin, side: str, x: float, py: float):
            # For the root sheet, the port is attached to the inner_body node
            port_parent_id = f"inner_body_{bid}" if sheet_id == "root" else bid
            elk_port_id = f"{port_parent_id}:{p.schematic_hierarchical_pin_id}"
            inner_ports.append({
                "id": elk_port_id, "x": x, "y": py, "width": 0, "height": 0, 
                "layoutOptions": {"org.eclipse.elk.port.side": side}
            })
            
            # Find labels for this pin
            pin_labels = [
                l for l in sheet_labels 
                if isinstance(l, (SchematicNetLabel, SchematicHierarchicalLabel)) 
                and getattr(l, 'schematic_hierarchical_pin_id', None) == p.schematic_hierarchical_pin_id
            ]
            for lbl in pin_labels:
                lbl_id = get_element_id(lbl)
                lbl_node_id = f"label_node_{lbl_id}"
                label_nodes.append({
                    "id": lbl_node_id, 
                    "width": len(lbl.text) * ElkSizingConfig.CHAR_WIDTH_PX, 
                    "height": ElkSizingConfig.LABEL_HEIGHT
                })
                edges.append({
                    "id": f"e_label_{lbl_id}",
                    "sources": [elk_port_id],
                    "targets": [lbl_node_id]
                })
                added_labels.add(lbl_id)

        for i, p in enumerate(west_pins):
            process_pin(p, "WEST", 0, (i + 1) * ElkSizingConfig.PIN_SPACING)
        for i, p in enumerate(east_pins):
            process_pin(p, "EAST", inner_bw, (i + 1) * ElkSizingConfig.PIN_SPACING)

        if sheet_id != "root":
            node: ElkNode = {
                "id": bid, "width": inner_bw, "height": inner_bh, "ports": inner_ports, 
                "layoutOptions": {"org.eclipse.elk.portConstraints": "FIXED_POS"}
            }
            return node, edges, label_nodes
        else:
            name_text = group.name or group.source_group_id
            file_text = f"File: {group.source_group_id.replace('box_', '')}.kicad_sch"
            node: ElkNode = {
                "id": bid,
                "children": [
                    {"id": f"text_name_{bid}", "width": len(name_text) * 10 + 60, "height": 40},
                    {
                        "id": f"inner_body_{bid}", 
                        "width": inner_bw, 
                        "height": inner_bh, 
                        "ports": inner_ports,
                        "layoutOptions": {"org.eclipse.elk.portConstraints": "FIXED_POS"}
                    },
                    {"id": f"text_file_{bid}", "width": len(file_text) * 8 + 60, "height": 40}
                ],
                "edges": [
                    {"id": f"edge_v1_{bid}", "sources": [f"text_name_{bid}"], "targets": [f"inner_body_{bid}"]},
                    {"id": f"edge_v2_{bid}", "sources": [f"inner_body_{bid}"], "targets": [f"text_file_{bid}"]},
                ],
                "layoutOptions": {
                    "org.eclipse.elk.algorithm": "layered",
                    "org.eclipse.elk.direction": "DOWN", 
                    "org.eclipse.elk.spacing.nodeNode": "100", 
                    "org.eclipse.elk.padding": "[top=100,left=50,bottom=100,right=50]"
                }
            }
            return node, edges, label_nodes

    def _build_connectivity_edges(
        self, 
        connectivity: List[Dict[str, Any]], 
        components: List[SourceComponent], 
        child_sheets: List[SourceGroup], 
        ports_by_comp: Dict[str, List[SourcePort]], 
        generated_elements: List[CircuitElement],
        sheet_id: str
    ) -> List[Dict[str, Any]]:
        edges = []
        port_to_elk_id = {}
        
        for comp in components:
            for p in ports_by_comp[comp.source_component_id]:
                port_to_elk_id[p.source_port_id] = f"{comp.source_component_id}:{p.source_port_id}"
        
        for group in child_sheets:
            bid = f"box_{group.source_group_id}"
            box_pins = [
                e for e in generated_elements 
                if isinstance(e, SchematicHierarchicalPin) and e.schematic_box_id == bid
            ]
            for p in box_pins:
                # If on the root sheet, the port is on the inner_body child
                port_parent_id = f"inner_body_{bid}" if sheet_id == "root" else bid
                port_to_elk_id[p.schematic_hierarchical_pin_id] = f"{port_parent_id}:{p.schematic_hierarchical_pin_id}"

        for conn in connectivity:
            sip = conn["ports"]
            if not sip: continue
            
            if not conn["is_inter_group"] and not conn["is_inter_sheet"]:
                src_elk_port = port_to_elk_id.get(sip[0])
                for target_port_id in sip[1:]: 
                    tgt_elk_port = port_to_elk_id.get(target_port_id)
                    if src_elk_port and tgt_elk_port:
                        edges.append({
                            "id": f"e_{conn['trace_id']}_{target_port_id}", 
                            "sources": [src_elk_port], 
                            "targets": [tgt_elk_port]
                        })
            
            if conn["is_inter_sheet"] and conn["hpin_id"]:
                src_elk_port = port_to_elk_id.get(sip[0])
                tgt_elk_port = port_to_elk_id.get(conn["hpin_id"])
                if src_elk_port and tgt_elk_port:
                    edges.append({
                        "id": f"e_to_hpin_{conn['trace_id']}", 
                        "sources": [src_elk_port], 
                        "targets": [tgt_elk_port]
                    })
        return edges

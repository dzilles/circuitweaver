import logging
from typing import Any, Dict, List
from circuitweaver.types.circuit_json import (
    CircuitElement, Point, SchematicNetLabel, SchematicHierarchicalLabel, 
    SchematicNoConnect, get_element_id
)
from .base import LayoutPlugin
from ..registry import LayoutContext
from ..models import LayoutNode, LayoutEdge

logger = logging.getLogger(__name__)

class AttachmentPlugin(LayoutPlugin):
    """Plugin for positioning labels and NC flags by 'sticking' them to ports."""

    def build(self, context: LayoutContext) -> None:
        for element in context.elements:
            if isinstance(element, (SchematicNetLabel, SchematicHierarchicalLabel)):
                self._build_label(element, context)
            elif isinstance(element, SchematicNoConnect):
                self._build_nc(element, context)

    def _build_label(self, element: Any, context: LayoutContext):
        # 1. Find the port this label is attached to
        port_id = getattr(element, "source_port_id", None) or getattr(element, "schematic_hierarchical_pin_id", None)
        if not port_id:
            return

        elk_port_id = context.registry.element_to_port.get(port_id)
        if not elk_port_id:
            return

        # 2. Create a node for the label
        eid = get_element_id(element)
        label_node_id = f"label_node_{eid}"
        
        # Labels are children of the node they attach to
        parent_id = elk_port_id.split(":")[0] if ":" in elk_port_id else None
        
        target_id = parent_id
        if parent_id and parent_id.startswith("box_"):
            target_id = f"inner_body_{parent_id}"
            
        parent_node = context.root_node.find_node(target_id) if target_id else None
        if parent_node is None:
            parent_node = context.root_node

        label_node = LayoutNode(
            id=label_node_id,
            width=len(element.text) * 7,
            height=10
        )
        parent_node.children.append(label_node)
        context.registry.register_node(element, label_node_id)

        # 3. Create an edge from port to label
        parent_node.edges.append(LayoutEdge(
            id=f"e_label_{eid}",
            sources=[elk_port_id],
            targets=[label_node_id]
        ))

    def _build_nc(self, element: SchematicNoConnect, context: LayoutContext):
        pid = element.schematic_port_id
        if pid and pid.startswith("port_"): pid = pid[5:]
        
        elk_port_id = context.registry.element_to_port.get(pid)
        if not elk_port_id:
            return

        eid = element.schematic_no_connect_id
        nc_node_id = f"nc_node_{eid}"
        
        parent_id = elk_port_id.split(":")[0] if ":" in elk_port_id else None
        
        target_id = parent_id
        if parent_id and parent_id.startswith("box_"):
            target_id = f"inner_body_{parent_id}"
            
        parent_node = context.root_node.find_node(target_id) if target_id else None
        if parent_node is None:
            parent_node = context.root_node
        
        nc_node = LayoutNode(id=nc_node_id, width=0, height=0)
        parent_node.children.append(nc_node)
        context.registry.register_node(element, nc_node_id)
        
        parent_node.edges.append(LayoutEdge(
            id=f"e_nc_{eid}",
            sources=[elk_port_id],
            targets=[nc_node_id]
        ))

    def apply(self, context: LayoutContext, results: Dict[str, Any]) -> List[CircuitElement]:
        positioned = []
        for element in context.elements:
            if isinstance(element, (SchematicNetLabel, SchematicHierarchicalLabel, SchematicNoConnect)):
                # Positions were already updated by ElkLayeredPlugin.apply
                # during its recursive traversal of the results tree.
                positioned.append(element)
        return positioned

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union
from circuitweaver.types.circuit_json import CircuitElement, SourcePort, SchematicPort, get_element_id

@dataclass
class LayoutContext:
    sheet_id: str
    elements: List[CircuitElement]
    root_node: "LayoutNode"
    registry: "MappingRegistry"
    symbol_map: Dict[str, "SymbolInfo"]
    sheet_connectivity: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

class MappingRegistry:
    """Tracks relationship between Circuit JSON elements and Layout objects."""
    
    def __init__(self):
        # Element ID -> Layout Node ID
        self.element_to_node: Dict[str, str] = {}
        # Element ID -> Layout Port ID (NodeID:PortID)
        self.element_to_port: Dict[str, str] = {}
        # Layout ID -> Element
        self.layout_to_element: Dict[str, CircuitElement] = {}

    def register_node(self, element: CircuitElement, node_id: str):
        eid = get_element_id(element)
        self.element_to_node[eid] = node_id
        self.layout_to_element[node_id] = element

    def register_port(self, element: Union[SourcePort, SchematicPort, "SchematicHierarchicalPin"], port_id: str):
        eid = get_element_id(element)
        self.element_to_port[eid] = port_id
        self.layout_to_element[port_id] = element

    def get_element_by_layout_id(self, layout_id: str) -> Optional[CircuitElement]:
        # Handle "parent:port" style IDs by stripping parent prefix
        base_id = layout_id.split(":")[-1]
        return self.layout_to_element.get(layout_id) or self.layout_to_element.get(base_id)

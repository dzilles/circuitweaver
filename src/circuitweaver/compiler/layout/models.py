from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class LayoutPort(BaseModel):
    id: str
    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0
    layoutOptions: Dict[str, Any] = Field(default_factory=dict)

class LayoutEdge(BaseModel):
    id: str
    sources: List[str]
    targets: List[str]
    sections: List[Dict[str, Any]] = Field(default_factory=list)
    layoutOptions: Dict[str, Any] = Field(default_factory=dict)

class LayoutNode(BaseModel):
    id: str
    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0
    ports: List[LayoutPort] = Field(default_factory=list)
    children: List["LayoutNode"] = Field(default_factory=list)
    edges: List[LayoutEdge] = Field(default_factory=list)
    layoutOptions: Dict[str, Any] = Field(default_factory=dict)

    def find_node(self, node_id: str) -> Optional["LayoutNode"]:
        if self.id == node_id:
            return self
        for child in self.children:
            found = child.find_node(node_id)
            if found:
                return found
        return None

# Required for recursive type LayoutNode
LayoutNode.model_rebuild()
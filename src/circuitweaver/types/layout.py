"""Pydantic models representing the ELK (Eclipse Layout Kernel) JSON Graph format.

These classes define the exact JSON schema expected by, and returned from,
the ELK Node.js layout engine. They serve as the intermediate representation
between Source types (logical netlist) and Schematic types (visual output).
"""

from typing import Any, Optional

from pydantic import BaseModel, Field

# =============================================================================
# Geometry Primitives
# =============================================================================

class LayoutPoint(BaseModel):
    """An X/Y coordinate pair used in ELK routing."""
    x: float
    y: float


class LayoutEdgeSection(BaseModel):
    """A routed wire segment returned by ELK, including bend points."""
    id: str
    startPoint: LayoutPoint
    endPoint: LayoutPoint
    bendPoints: list[LayoutPoint] = Field(default_factory=list)


# =============================================================================
# Graph Elements
# =============================================================================

class LayoutLabel(BaseModel):
    """A text label attached to a node (e.g., reference designator, component value)."""
    id: str
    text: str
    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0
    layoutOptions: dict[str, Any] = Field(default_factory=dict)


class LayoutPort(BaseModel):
    """A connection point on a node (represents a pin on a component)."""
    id: str
    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0
    layoutOptions: dict[str, Any] = Field(default_factory=dict)


class LayoutEdge(BaseModel):
    """A connection between two ports (represents a trace/wire)."""
    id: str
    sources: list[str]
    targets: list[str]
    sections: list[LayoutEdgeSection] = Field(default_factory=list)
    layoutOptions: dict[str, Any] = Field(default_factory=dict)


class LayoutNode(BaseModel):
    """A bounding box in the layout (represents a component or hierarchical sheet)."""
    id: str
    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0
    labels: list[LayoutLabel] = Field(default_factory=list)
    ports: list[LayoutPort] = Field(default_factory=list)
    children: list["LayoutNode"] = Field(default_factory=list)
    edges: list[LayoutEdge] = Field(default_factory=list)
    layoutOptions: dict[str, Any] = Field(default_factory=dict)

    def find_node(self, node_id: str) -> Optional["LayoutNode"]:
        """Recursively find a child node by its ID."""
        if self.id == node_id:
            return self
        for child in self.children:
            found = child.find_node(node_id)
            if found:
                return found
        return None


# Required for recursive type LayoutNode
LayoutNode.model_rebuild()

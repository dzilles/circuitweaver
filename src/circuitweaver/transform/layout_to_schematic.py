"""Transform Layout graph to Schematic elements.

Transforms Layout types (ELK graph with positions) into Schematic types
(visual elements with coordinates).
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from circuitweaver.types import (
    CircuitElement,
    LayoutNode,
    Point,
    SchematicBox,
    SchematicComponent,
    SchematicHierarchicalLabel,
    SchematicHierarchicalPin,
    SchematicNetLabel,
    SchematicNoConnect,
    SchematicPort,
    SchematicTrace,
    SchematicTraceEdge,
    SourceComponent,
    SourceGroup,
    SourcePort,
    get_element_id,
)
from circuitweaver.transform.source_to_layout import LayoutRegistry, get_effective_symbol_id

logger = logging.getLogger(__name__)


# =============================================================================
# Grid Snapping
# =============================================================================

def snap_to_grid(value: float, grid_size: float = 10.0) -> float:
    """Snap a value to the nearest grid point.

    Args:
        value: The value to snap.
        grid_size: Grid spacing (default 10 = KiCad 50 mils).

    Returns:
        Snapped value.
    """
    return float(round(value / grid_size) * grid_size)


# =============================================================================
# Transform
# =============================================================================

class LayoutToSchematicTransform:
    """Transforms ELK Layout results into Schematic elements.

    Takes a positioned LayoutNode graph (output from ELK) and creates
    positioned Schematic elements.
    """

    def __init__(
        self,
        symbol_map: Optional[Dict[str, Any]] = None,
        grid_size: float = 10.0,
    ):
        """Initialize the transform.

        Args:
            symbol_map: Dictionary mapping symbol_id to SymbolInfo.
            grid_size: Grid spacing for snapping coordinates.
        """
        self.symbol_map = symbol_map or {}
        self.grid_size = grid_size

    def transform(
        self,
        sheet_id: str,
        layout_result: LayoutNode,
        registry: LayoutRegistry,
        elements: List[CircuitElement],
    ) -> List[CircuitElement]:
        """Transform ELK layout results into Schematic elements.

        Args:
            sheet_id: ID of the sheet being processed.
            layout_result: Root LayoutNode with positions from ELK.
            registry: Mapping between elements and layout IDs.
            elements: Original circuit elements for this sheet.

        Returns:
            List of positioned Schematic elements.
        """
        final_elements: List[CircuitElement] = []

        def snap(v: float) -> float:
            return snap_to_grid(v, self.grid_size)

        # Process nodes
        for child in layout_result.children:
            self._process_node(child, 0, 0, sheet_id, registry, elements, final_elements, snap)

        # Process edges
        self._process_edges(layout_result, 0, 0, sheet_id, registry, elements, final_elements, snap)

        return final_elements

    def _process_node(
        self,
        node: LayoutNode,
        parent_x: float,
        parent_y: float,
        sheet_id: str,
        registry: LayoutRegistry,
        elements: List[CircuitElement],
        final_elements: List[CircuitElement],
        snap: Callable[[float], float],
    ) -> None:
        """Process a layout node and create schematic elements."""
        nid = node.id
        raw_x = node.x + parent_x
        raw_y = node.y + parent_y
        snapped_x, snapped_y = snap(raw_x), snap(raw_y)

        element = registry.get_element_by_layout_id(nid)

        if isinstance(element, SourceComponent):
            self._build_component(
                element, node, raw_x, raw_y, snapped_x, snapped_y,
                sheet_id, elements, final_elements, snap,
            )
            for child in node.children:
                self._process_node(child, raw_x, raw_y, sheet_id, registry, elements, final_elements, snap)

        elif isinstance(element, SourceGroup):
            self._build_box(
                element, node, raw_x, raw_y, snapped_x, snapped_y,
                sheet_id, elements, final_elements, snap,
            )
            for child in node.children:
                self._process_node(child, raw_x, raw_y, sheet_id, registry, elements, final_elements, snap)

        elif isinstance(element, (SchematicNetLabel, SchematicHierarchicalLabel)):
            # Labels are positioned via edge parsing
            pass

        elif isinstance(element, SchematicNoConnect):
            # No-connects are positioned when processing components
            pass

        else:
            for child in node.children:
                self._process_node(child, raw_x, raw_y, sheet_id, registry, elements, final_elements, snap)

    def _build_component(
        self,
        comp: SourceComponent,
        node: LayoutNode,
        raw_x: float,
        raw_y: float,
        snapped_x: float,
        snapped_y: float,
        sheet_id: str,
        elements: List[CircuitElement],
        final_elements: List[CircuitElement],
        snap: Callable[[float], float],
    ) -> None:
        """Build SchematicComponent and ports from a component node."""
        nid = node.id
        symbol_id = get_effective_symbol_id(comp)
        symbol = self.symbol_map.get(symbol_id) if symbol_id else None

        # Calculate component center
        offset = symbol.bounding_box_min if symbol else Point(x=0, y=0)
        cx, cy = snap(raw_x - offset.x), snap(raw_y - offset.y)

        final_elements.append(SchematicComponent(
            schematic_component_id=f"sch_{nid}",
            sheet_id=sheet_id,
            source_component_id=nid,
            center=Point(x=cx, y=cy),
        ))

        # Build ports
        comp_ports = [e for e in elements if isinstance(e, SourcePort) and e.source_component_id == nid]
        symbol_pins = {str(p.number): p for p in symbol.pins} if symbol else {}
        source_port_pins = set()

        for port in comp_ports:
            pin_info = symbol_pins.get(str(port.pin_number)) or next(
                (p for p in symbol_pins.values() if p.name == port.name), None
            )
            if pin_info:
                source_port_pins.add(str(pin_info.number))
                px = snap(raw_x + (pin_info.grid_offset.x - symbol.bounding_box_min.x))
                py = snap(raw_y + (pin_info.grid_offset.y - symbol.bounding_box_min.y))

                final_elements.append(SchematicPort(
                    schematic_port_id=f"port_{get_element_id(port)}",
                    source_port_id=port.source_port_id,
                    sheet_id=sheet_id,
                    center=Point(x=px, y=py),
                ))

                # Position attached no-connects
                for nc in elements:
                    if isinstance(nc, SchematicNoConnect) and nc.schematic_port_id == port.source_port_id:
                        nc.position = Point(x=px, y=py)

        # Position no-connects for pins without source_ports
        for nc in elements:
            if isinstance(nc, SchematicNoConnect) and nc.schematic_port_id and "-" in nc.schematic_port_id:
                nc_comp_id, nc_pin_num = nc.schematic_port_id.rsplit("-", 1)
                if nc_comp_id == nid and nc_pin_num not in source_port_pins:
                    pin_info = symbol_pins.get(nc_pin_num)
                    if pin_info:
                        px = snap(raw_x + (pin_info.grid_offset.x - symbol.bounding_box_min.x))
                        py = snap(raw_y + (pin_info.grid_offset.y - symbol.bounding_box_min.y))
                        nc.position = Point(x=px, y=py)

    def _build_box(
        self,
        group: SourceGroup,
        node: LayoutNode,
        raw_x: float,
        raw_y: float,
        snapped_x: float,
        snapped_y: float,
        sheet_id: str,
        elements: List[CircuitElement],
        final_elements: List[CircuitElement],
        snap: Callable[[float], float],
    ) -> None:
        """Build SchematicBox from a group node."""
        nid = node.id
        box_width = snap(node.width)
        box_height = snap(node.height)

        # Position hierarchical pins from port data
        for port in node.ports:
            actual_id = port.id.split(":", 1)[1] if ":" in port.id else port.id
            hpin = next(
                (e for e in elements
                 if isinstance(e, SchematicHierarchicalPin) and e.schematic_hierarchical_pin_id == actual_id),
                None,
            )
            if hpin:
                hpin.center = Point(x=snap(raw_x + port.x), y=snap(raw_y + port.y))

        final_elements.append(SchematicBox(
            schematic_box_id=nid,
            sheet_id=sheet_id,
            x=snapped_x,
            y=snapped_y,
            width=box_width,
            height=box_height,
            is_hierarchical_sheet=bool(group.is_subcircuit),
            child_sheet_id=group.subcircuit_id if group.is_subcircuit else None,
            name=group.name,
        ))

    def _process_edges(
        self,
        node: LayoutNode,
        parent_x: float,
        parent_y: float,
        sheet_id: str,
        registry: LayoutRegistry,
        elements: List[CircuitElement],
        final_elements: List[CircuitElement],
        snap: Callable[[float], float],
    ) -> None:
        """Process edges recursively and create traces."""
        raw_x, raw_y = node.x + parent_x, node.y + parent_y

        for edge in node.edges:
            eid = edge.id

            # Skip virtual edges
            if eid.startswith("edge_v"):
                continue

            source_trace_id = None

            # Handle label edges
            if eid.startswith("e_label_"):
                label_id = eid.replace("e_label_", "")
                label = registry.get_element_by_layout_id(f"label_node_{label_id}")

                if isinstance(label, (SchematicNetLabel, SchematicHierarchicalLabel)):
                    if edge.sections:
                        section = edge.sections[0]
                        endpoint = section.endPoint
                        label.center = Point(x=snap(endpoint.x + raw_x), y=snap(endpoint.y + raw_y))

                        # Calculate anchor side from direction
                        points = [section.startPoint] + list(section.bendPoints) + [section.endPoint]
                        if len(points) >= 2:
                            p2, p1 = points[-1], points[-2]
                            dx, dy = p2.x - p1.x, p2.y - p1.y
                            if abs(dx) > abs(dy):
                                label.anchor_side = "left" if dx > 0 else "right"
                            else:
                                label.anchor_side = "top" if dy > 0 else "bottom"

                    # Only append if not already in final_elements
                    if not any(get_element_id(e) == get_element_id(label) for e in final_elements):
                        final_elements.append(label)

                source_trace_id = getattr(label, "source_net_id", None) if label else None

            # Skip no-connect edges
            elif eid.startswith("e_nc_"):
                continue

            # Regular edges
            elif eid.startswith("e_"):
                parts = eid.split("_")
                if len(parts) >= 4 and parts[1] == "to" and parts[2] == "hpin":
                    source_trace_id = parts[3]
                else:
                    source_trace_id = parts[1]

            # Build traces from sections
            for section in edge.sections:
                points = [Point(x=snap(section.startPoint.x + raw_x), y=snap(section.startPoint.y + raw_y))]
                points.extend([Point(x=snap(bp.x + raw_x), y=snap(bp.y + raw_y)) for bp in section.bendPoints])
                points.append(Point(x=snap(section.endPoint.x + raw_x), y=snap(section.endPoint.y + raw_y)))

                # Create trace edges, skipping zero-length segments
                trace_edges = []
                for i in range(len(points) - 1):
                    if points[i].x != points[i + 1].x or points[i].y != points[i + 1].y:
                        trace_edges.append(SchematicTraceEdge.model_validate({
                            "from": points[i],
                            "to": points[i + 1],
                        }))

                if trace_edges:
                    final_elements.append(SchematicTrace(
                        schematic_trace_id=f"sch_{eid}_{id(section)}",
                        source_trace_id=source_trace_id,
                        sheet_id=sheet_id,
                        edges=trace_edges,
                    ))

        # Recurse into children
        for child in node.children:
            self._process_edges(
                child, raw_x, raw_y,
                sheet_id, registry, elements, final_elements, snap,
            )

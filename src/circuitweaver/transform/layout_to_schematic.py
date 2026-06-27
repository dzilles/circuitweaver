"""Transform Layout graph to Schematic elements.

Transforms Layout types (ELK graph with positions) into Schematic types
(visual elements with coordinates).
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from circuitweaver.transform.source_to_layout import LayoutRegistry, get_effective_symbol_id
from circuitweaver.types import (
    SOURCE_TRACE_ID_LAYOUT_OPTION,
    CircuitElement,
    LayoutEdge,
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

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Bounds:
    x1: float
    y1: float
    x2: float
    y2: float


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
        symbol_map: dict[str, Any] | None = None,
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
        elements: list[CircuitElement],
    ) -> list[CircuitElement]:
        """Transform ELK layout results into Schematic elements.

        Args:
            sheet_id: ID of the sheet being processed.
            layout_result: Root LayoutNode with positions from ELK.
            registry: Mapping between elements and layout IDs.
            elements: Original circuit elements for this sheet.

        Returns:
            List of positioned Schematic elements.
        """
        final_elements: list[CircuitElement] = []

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
        elements: list[CircuitElement],
        final_elements: list[CircuitElement],
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
                sheet_id, registry, elements, final_elements, snap,
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
        _snapped_x: float,
        _snapped_y: float,
        sheet_id: str,
        registry: LayoutRegistry,
        elements: list[CircuitElement],
        final_elements: list[CircuitElement],
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
        layout_ports = {p.id: p for p in node.ports}

        for port in comp_ports:
            pin_info = symbol_pins.get(str(port.pin_number)) or next(
                (p for p in symbol_pins.values() if p.name == port.name), None
            )
            if pin_info:
                source_port_pins.add(str(pin_info.number))
                px = snap(raw_x + (pin_info.grid_offset.x - symbol.bounding_box_min.x))
                py = snap(raw_y + (pin_info.grid_offset.y - symbol.bounding_box_min.y))
            else:
                layout_port = layout_ports.get(f"{nid}:{port.pin_number}")
                if layout_port is None:
                    layout_port = layout_ports.get(f"{nid}:{port.name}")
                if layout_port is None:
                    layout_port = next(
                        (p for p in layout_ports.values() if registry.get_element_by_layout_id(p.id) == port),
                        None,
                    )
                if layout_port is None:
                    continue
                px = snap(raw_x + layout_port.x)
                py = snap(raw_y + layout_port.y)

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
        elements: list[CircuitElement],
        final_elements: list[CircuitElement],
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
                for label in (
                    e for e in elements
                    if isinstance(e, SchematicNetLabel)
                    and e.schematic_hierarchical_pin_id == hpin.schematic_hierarchical_pin_id
                ):
                    label.center = hpin.center
                    label.anchor_side = "right" if port.x <= 0 else "left"

        final_elements.append(SchematicBox(
            schematic_box_id=nid,
            sheet_id=sheet_id,
            x=snapped_x,
            y=snapped_y,
            width=box_width,
            height=box_height,
            is_hierarchical_sheet=bool(group.is_subcircuit),
            child_sheet_id=(group.subcircuit_id or group.source_group_id) if group.is_subcircuit else None,
            name=group.name,
        ))

    def _process_edges(
        self,
        node: LayoutNode,
        parent_x: float,
        parent_y: float,
        sheet_id: str,
        registry: LayoutRegistry,
        elements: list[CircuitElement],
        final_elements: list[CircuitElement],
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
                    else:
                        source_point = self._find_port_position(node, raw_x, raw_y, edge.sources[0])
                        if source_point is not None:
                            label.center = Point(x=snap(source_point.x + 10), y=snap(source_point.y))
                            label.anchor_side = "left"
                        else:
                            label_node = node.find_node(f"label_node_{label_id}")
                            if label_node is not None:
                                label.center = Point(
                                    x=snap(raw_x + label_node.x),
                                    y=snap(raw_y + label_node.y),
                                )

                    # Only append if not already in final_elements
                    if not any(get_element_id(e) == get_element_id(label) for e in final_elements):
                        final_elements.append(label)

                source_trace_id = getattr(label, "source_net_id", None) if label else None

            # Skip no-connect edges
            elif eid.startswith("e_nc_"):
                continue

            # Regular edges
            elif eid.startswith("e_"):
                source_trace_id = self._source_trace_id_for_edge(edge)

            # Build traces from sections
            for section in edge.sections:
                points = [Point(x=snap(section.startPoint.x + raw_x), y=snap(section.startPoint.y + raw_y))]
                points.extend([Point(x=snap(bp.x + raw_x), y=snap(bp.y + raw_y)) for bp in section.bendPoints])
                points.append(Point(x=snap(section.endPoint.x + raw_x), y=snap(section.endPoint.y + raw_y)))

                # Create trace edges, skipping zero-length segments
                trace_edges = []
                for i in range(len(points) - 1):
                    if points[i].x != points[i + 1].x or points[i].y != points[i + 1].y:
                        trace_edges.extend(self._orthogonal_edges(points[i], points[i + 1]))

                if trace_edges:
                    trace_edges = self._avoid_component_bounds(
                        trace_edges,
                        sheet_id,
                        elements,
                        final_elements,
                    )
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

    @staticmethod
    def _source_trace_id_for_edge(edge: LayoutEdge) -> str | None:
        source_trace_id = edge.layoutOptions.get(SOURCE_TRACE_ID_LAYOUT_OPTION)
        if source_trace_id:
            return str(source_trace_id)

        if edge.id.startswith("e_to_hpin_"):
            return edge.id.removeprefix("e_to_hpin_")
        if edge.id.startswith("e_"):
            return edge.id.removeprefix("e_")
        return None

    def _find_port_position(
        self,
        node: LayoutNode,
        parent_x: float,
        parent_y: float,
        port_id: str,
    ) -> Point | None:
        for port in node.ports:
            if port.id == port_id:
                return Point(x=parent_x + port.x, y=parent_y + port.y)
        for child in node.children:
            found = self._find_port_position(child, parent_x + child.x, parent_y + child.y, port_id)
            if found is not None:
                return found
        return None

    @staticmethod
    def _orthogonal_edges(start: Point, end: Point) -> list[SchematicTraceEdge]:
        if start.x == end.x or start.y == end.y:
            return [SchematicTraceEdge.model_validate({"from": start, "to": end})]

        elbow = Point(x=end.x, y=start.y)
        return [
            SchematicTraceEdge.model_validate({"from": start, "to": elbow}),
            SchematicTraceEdge.model_validate({"from": elbow, "to": end}),
        ]

    def _avoid_component_bounds(
        self,
        trace_edges: list[SchematicTraceEdge],
        sheet_id: str,
        source_elements: list[CircuitElement],
        final_elements: list[CircuitElement],
    ) -> list[SchematicTraceEdge]:
        component_bounds = self._component_bounds_by_sheet(source_elements, final_elements, sheet_id)
        if not component_bounds:
            return trace_edges

        routed: list[SchematicTraceEdge] = []
        for edge in trace_edges:
            replacement = [edge]
            for bounds in component_bounds:
                next_replacement: list[SchematicTraceEdge] = []
                for candidate in replacement:
                    next_replacement.extend(self._detour_around_bounds(candidate, bounds))
                replacement = next_replacement
            routed.extend(replacement)
        return routed

    def _component_bounds_by_sheet(
        self,
        source_elements: list[CircuitElement],
        final_elements: list[CircuitElement],
        sheet_id: str,
    ) -> list[_Bounds]:
        sources = {
            e.source_component_id: e for e in source_elements if isinstance(e, SourceComponent)
        }
        bounds: list[_Bounds] = []
        for comp in final_elements:
            if not isinstance(comp, SchematicComponent) or comp.sheet_id != sheet_id:
                continue
            source = sources.get(comp.source_component_id)
            symbol = None
            if source:
                symbol_id = get_effective_symbol_id(source)
                symbol = self.symbol_map.get(symbol_id) if symbol_id else None
            width = getattr(symbol, "width", 40)
            height = getattr(symbol, "height", 40)
            bounds.append(
                _Bounds(
                    comp.center.x - width / 2,
                    comp.center.y - height / 2,
                    comp.center.x + width / 2,
                    comp.center.y + height / 2,
                )
            )
        return bounds

    @staticmethod
    def _detour_around_bounds(edge: SchematicTraceEdge, bounds: _Bounds) -> list[SchematicTraceEdge]:
        start = edge.from_
        end = edge.to
        margin = 20
        if start.y == end.y and bounds.y1 < start.y < bounds.y2:
            x1, x2 = sorted((start.x, end.x))
            if x1 < bounds.x2 and x2 > bounds.x1:
                detour_y = bounds.y1 - margin
                p1 = Point(x=start.x, y=detour_y)
                p2 = Point(x=end.x, y=detour_y)
                return [
                    SchematicTraceEdge.model_validate({"from": start, "to": p1}),
                    SchematicTraceEdge.model_validate({"from": p1, "to": p2}),
                    SchematicTraceEdge.model_validate({"from": p2, "to": end}),
                ]
        if start.x == end.x and bounds.x1 < start.x < bounds.x2:
            y1, y2 = sorted((start.y, end.y))
            if y1 < bounds.y2 and y2 > bounds.y1:
                detour_x = bounds.x1 - margin
                p1 = Point(x=detour_x, y=start.y)
                p2 = Point(x=detour_x, y=end.y)
                return [
                    SchematicTraceEdge.model_validate({"from": start, "to": p1}),
                    SchematicTraceEdge.model_validate({"from": p1, "to": p2}),
                    SchematicTraceEdge.model_validate({"from": p2, "to": end}),
                ]
        return [edge]

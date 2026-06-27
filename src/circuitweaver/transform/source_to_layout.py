"""Transform Source elements to Layout graph.

Transforms Source types (logical netlist) into Layout types (ELK graph)
that can be processed by the ELK layout engine.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from circuitweaver.types import (
    CircuitElement,
    LayoutEdge,
    LayoutNode,
    LayoutPort,
    Point,
    SchematicHierarchicalLabel,
    SchematicHierarchicalPin,
    SchematicNetLabel,
    SchematicNoConnect,
    SourceComponent,
    SourceGroup,
    SourcePort,
    get_element_id,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================


class LayoutSizingConfig:
    """Default sizes for layout elements."""

    PIN_SPACING = 20
    MIN_BOX_WIDTH = 250
    MIN_BOX_HEIGHT = 100
    GROUP_PADDING = 40


# Mapping from ftype to KiCad symbol_id for inference
FTYPE_SYMBOL_MAP = {
    "simple_resistor": "Device:R",
    "simple_capacitor": "Device:C",
    "simple_led": "Device:LED",
    "simple_diode": "Device:D",
    "simple_transistor": "Device:Q_NPN_BCE",
}


def get_effective_symbol_id(comp: SourceComponent) -> str | None:
    """Get the effective symbol_id for a component, falling back to ftype inference."""
    return comp.symbol_id or FTYPE_SYMBOL_MAP.get(comp.ftype)


# =============================================================================
# Registry for Element-to-Layout Mapping
# =============================================================================


class LayoutRegistry:
    """Tracks bidirectional mapping between CircuitElements and Layout IDs.

    Used during transformation to track which layout nodes/ports correspond
    to which source elements.
    """

    def __init__(self):
        self.element_to_node: dict[str, str] = {}
        self.element_to_port: dict[str, str] = {}
        self.layout_to_element: dict[str, CircuitElement] = {}

    def register_node(self, element: CircuitElement, node_id: str) -> None:
        """Register a node mapping."""
        eid = get_element_id(element)
        self.element_to_node[eid] = node_id
        self.layout_to_element[node_id] = element

    def register_port(self, element: CircuitElement, port_id: str) -> None:
        """Register a port mapping."""
        eid = get_element_id(element)
        self.element_to_port[eid] = port_id
        self.layout_to_element[port_id] = element

    def get_element_by_layout_id(self, layout_id: str) -> CircuitElement | None:
        """Look up element by layout ID, handling 'parent:port' format."""
        base_id = layout_id.split(":")[-1]
        return self.layout_to_element.get(layout_id) or self.layout_to_element.get(base_id)


# =============================================================================
# Transform
# =============================================================================


@dataclass
class _TransformContext:
    """Internal context passed during transformation."""

    sheet_id: str
    elements: list[CircuitElement]
    root_node: LayoutNode
    registry: LayoutRegistry
    symbol_map: dict[str, Any]  # symbol_id -> SymbolInfo
    sheet_connectivity: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    # Map of element_id -> Parent LayoutNode
    node_map: dict[str, LayoutNode] = field(default_factory=dict)


class SourceToLayoutTransform:
    """Transforms Source elements into an ELK Layout graph.

    Supports hierarchical nesting of groups and smart connectivity (wires vs labels).
    """

    def __init__(self, symbol_map: dict[str, Any] | None = None):
        """Initialize with optional symbol info map."""
        self.symbol_map = symbol_map or {}

    def transform(
        self,
        sheet_id: str,
        elements: list[CircuitElement],
        sheet_connectivity: dict[str, list[dict[str, Any]]] | None = None,
    ) -> tuple[LayoutNode, LayoutRegistry]:
        """Transform source elements into a LayoutNode graph."""
        registry = LayoutRegistry()
        root_node = LayoutNode(
            id=sheet_id,
            layoutOptions={
                "org.eclipse.elk.algorithm": "layered",
                "org.eclipse.elk.direction": "RIGHT",
                "org.eclipse.elk.padding": "[top=100,left=100,bottom=100,right=100]",
                "org.eclipse.elk.layered.spacing.nodeNode": "50",
                "org.eclipse.elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
            },
        )

        ctx = _TransformContext(
            sheet_id=sheet_id,
            elements=elements,
            root_node=root_node,
            registry=registry,
            symbol_map=self.symbol_map,
            sheet_connectivity=sheet_connectivity or {},
        )
        ctx.node_map[sheet_id] = root_node

        # 1. Build hierarchy (Boxes for sub-sheets and subgroups)
        self._build_node_hierarchy(ctx)

        # 2. Add components into their respective containers
        self._add_components(ctx)

        # 3. Build connectivity (Wires vs Labels)
        self._add_connectivity(ctx)

        # 4. Add attachments (No-connects, etc.)
        self._add_attachments(ctx)

        # 5. Apply deterministic flow ordering and container sizing.
        self._apply_flow_ordering(ctx)
        self._resize_group_nodes(ctx.root_node)

        return root_node, registry

    def _build_node_hierarchy(self, ctx: _TransformContext) -> None:
        """Create LayoutNodes for all groups (subcircuits and subgroups)."""
        groups = sorted(
            [e for e in ctx.elements if isinstance(e, SourceGroup)],
            key=lambda g: g.source_group_id,
        )

        # Sort groups by parent dependency to build bottom-up if needed,
        # but here we'll just find parents recursively.
        processed: set[str] = set()

        def ensure_group_node(group: SourceGroup) -> LayoutNode:
            if group.source_group_id in processed:
                return ctx.node_map[f"box_{group.source_group_id}"]

            # Determine parent node
            parent_node = ctx.root_node
            if group.parent_source_group_id:
                parent_group = next(
                    (g for g in groups if g.source_group_id == group.parent_source_group_id), None
                )
                if parent_group:
                    parent_node = ensure_group_node(parent_group)

            # Create the node
            box_id = f"box_{group.source_group_id}"

            # Sub-sheets get special ports for hierarchical connections
            ports = []
            if group.is_subcircuit:
                ports = self._create_hierarchical_ports(group, ctx)

            node = LayoutNode(
                id=box_id,
                width=LayoutSizingConfig.MIN_BOX_WIDTH,
                height=self._minimum_group_height(len(ports)),
                ports=ports,
                layoutOptions={"org.eclipse.elk.portConstraints": "FIXED_POS"},
            )

            parent_node.children.append(node)
            ctx.node_map[box_id] = node
            ctx.registry.register_node(group, box_id)
            processed.add(group.source_group_id)
            return node

        for g in groups:
            ensure_group_node(g)

    def _create_hierarchical_ports(
        self, group: SourceGroup, ctx: _TransformContext
    ) -> list[LayoutPort]:
        """Create ports on a sub-sheet box for hierarchical pins."""
        box_id = f"box_{group.source_group_id}"
        hpins = sorted(
            [
                e
                for e in ctx.elements
                if isinstance(e, SchematicHierarchicalPin) and e.schematic_box_id == box_id
            ],
            key=lambda hpin: hpin.schematic_hierarchical_pin_id,
        )

        ports = []
        for i, hpin in enumerate(hpins):
            # Alternate sides
            side = "WEST" if i % 2 == 0 else "EAST"
            px = 0 if side == "WEST" else LayoutSizingConfig.MIN_BOX_WIDTH
            py = (i // 2 + 1) * LayoutSizingConfig.PIN_SPACING

            port_id = f"{box_id}:{hpin.schematic_hierarchical_pin_id}"
            ports.append(
                LayoutPort(
                    id=port_id,
                    x=px,
                    y=py,
                    layoutOptions={"org.eclipse.elk.port.side": side},
                )
            )
            ctx.registry.register_port(hpin, port_id)

        return ports

    def _add_components(self, ctx: _TransformContext) -> None:
        """Add components to their parent nodes."""
        components = sorted(
            [e for e in ctx.elements if isinstance(e, SourceComponent)],
            key=lambda comp: comp.source_component_id,
        )
        for comp in components:
            # Find the correct parent node (subgroup box or root)
            parent_id = f"box_{comp.source_group_id}" if comp.source_group_id else ctx.sheet_id
            parent_node = ctx.node_map.get(parent_id, ctx.root_node)

            symbol_id = get_effective_symbol_id(comp)
            symbol = self.symbol_map.get(symbol_id)
            width, height = (symbol.width, symbol.height) if symbol else (40, 40)

            ports = []
            if symbol:
                for pin_info in symbol.pins:
                    px = float(pin_info.grid_offset.x - symbol.bounding_box_min.x)
                    py = float(pin_info.grid_offset.y - symbol.bounding_box_min.y)

                    port_id = f"{comp.source_component_id}:{pin_info.number}"
                    ports.append(LayoutPort(id=port_id, x=px, y=py))

                    # Map source_port to this ELK port
                    source_port = next(
                        (
                            p
                            for p in ctx.elements
                            if isinstance(p, SourcePort)
                            and p.source_component_id == comp.source_component_id
                            and (
                                str(p.pin_number) == str(pin_info.number)
                                or (
                                    p.pin_number is None
                                    and getattr(pin_info, "name", None) is not None
                                    and p.name == pin_info.name
                                )
                            )
                        ),
                        None,
                    )
                    if source_port:
                        ctx.registry.register_port(source_port, port_id)
            else:
                # If no symbol info, create ports based on SourcePorts found in elements
                comp_ports = sorted(
                    [
                        p
                        for p in ctx.elements
                        if isinstance(p, SourcePort)
                        and p.source_component_id == comp.source_component_id
                    ],
                    key=lambda p: (str(p.pin_number or ""), p.source_port_id),
                )
                for i, sp in enumerate(comp_ports):
                    port_id = f"{comp.source_component_id}:{sp.pin_number}"
                    # Default positions for generic symbols
                    ports.append(
                        LayoutPort(
                            id=port_id,
                            x=0,
                            y=i * LayoutSizingConfig.PIN_SPACING,
                            layoutOptions={"org.eclipse.elk.port.side": "WEST"},
                        )
                    )
                    ctx.registry.register_port(sp, port_id)

            node = LayoutNode(
                id=comp.source_component_id,
                width=width,
                height=height,
                ports=ports,
                layoutOptions={"org.eclipse.elk.portConstraints": "FIXED_POS"},
            )
            parent_node.children.append(node)
            ctx.registry.register_node(comp, comp.source_component_id)

    def _apply_flow_ordering(self, ctx: _TransformContext) -> None:
        """Sort nodes by inferred signal flow, falling back to stable IDs."""
        outgoing = self._build_flow_edges(ctx)

        def sort_children(node: LayoutNode) -> None:
            if node.children:
                ids = [child.id for child in node.children]
                ranks = self._topological_ranks(ids, outgoing)
                node.children.sort(key=lambda child: (ranks.get(child.id, 0), child.id))
            for child in node.children:
                sort_children(child)

        sort_children(ctx.root_node)

        for source, targets in sorted(outgoing.items()):
            for target in sorted(targets):
                source_parent = self._get_parent_node_for_elk_id(source, ctx)
                target_parent = self._get_parent_node_for_elk_id(target, ctx)
                if source_parent is target_parent:
                    source_parent.edges.append(
                        LayoutEdge(
                            id=f"edge_v_order_{source}_{target}",
                            sources=[source],
                            targets=[target],
                        )
                    )

    def _build_flow_edges(self, ctx: _TransformContext) -> dict[str, set[str]]:
        """Infer directed node edges from connection endpoint roles."""
        port_map = {
            e.source_port_id: e for e in ctx.elements if isinstance(e, SourcePort)
        }
        component_to_node = {
            e.source_component_id: e.source_component_id
            for e in ctx.elements
            if isinstance(e, SourceComponent)
        }
        hpin_to_box = {
            e.schematic_hierarchical_pin_id: e.schematic_box_id
            for e in ctx.elements
            if isinstance(e, SchematicHierarchicalPin)
        }
        outgoing: dict[str, set[str]] = {}

        for conn in ctx.sheet_connectivity.get(ctx.sheet_id, []):
            endpoint_ids = sorted(conn.get("ports", []))
            endpoints: list[tuple[str, str]] = []
            for endpoint_id in endpoint_ids:
                port = port_map.get(endpoint_id)
                if port and port.source_component_id in component_to_node:
                    endpoints.append((component_to_node[port.source_component_id], self._port_role(port)))
            hpin_id = conn.get("hpin_id")
            if hpin_id and hpin_id in hpin_to_box:
                endpoints.append((hpin_to_box[hpin_id], "unknown"))

            sources = [node_id for node_id, role in endpoints if role == "output"]
            targets = [node_id for node_id, role in endpoints if role == "input"]
            if not sources and endpoints:
                sources = [endpoints[0][0]]
            if not targets:
                targets = [node_id for node_id, _role in endpoints if node_id not in sources]
            for source in sources:
                for target in targets:
                    if source != target:
                        outgoing.setdefault(source, set()).add(target)

        # Root-page sheet boxes may only have hierarchical pins available.
        box_pins = sorted(
            [e for e in ctx.elements if isinstance(e, SchematicHierarchicalPin)],
            key=lambda pin: pin.schematic_hierarchical_pin_id,
        )
        by_net: dict[str, list[SchematicHierarchicalPin]] = {}
        for pin in box_pins:
            by_net.setdefault(pin.source_net_id, []).append(pin)
        for pins in by_net.values():
            source_boxes = [
                pin.schematic_box_id for pin in pins if self._text_role(pin.text) == "output"
            ]
            target_boxes = [
                pin.schematic_box_id for pin in pins if self._text_role(pin.text) == "input"
            ]
            if not source_boxes and pins:
                source_boxes = [pins[0].schematic_box_id]
            if not target_boxes:
                target_boxes = [
                    pin.schematic_box_id for pin in pins if pin.schematic_box_id not in source_boxes
                ]
            for source in source_boxes:
                for target in target_boxes:
                    if source != target:
                        outgoing.setdefault(source, set()).add(target)

        return outgoing

    @staticmethod
    def _topological_ranks(node_ids: list[str], outgoing: dict[str, set[str]]) -> dict[str, int]:
        remaining = set(node_ids)
        incoming = dict.fromkeys(node_ids, 0)
        for source, targets in outgoing.items():
            if source not in remaining:
                continue
            for target in targets:
                if target in remaining:
                    incoming[target] += 1

        ranks: dict[str, int] = {}
        rank = 0
        while remaining:
            ready = sorted(node_id for node_id in remaining if incoming[node_id] == 0)
            if not ready:
                ready = [min(remaining)]
            for node_id in ready:
                ranks[node_id] = rank
                remaining.remove(node_id)
                for target in outgoing.get(node_id, set()):
                    if target in incoming:
                        incoming[target] -= 1
                rank += 1
        return ranks

    @staticmethod
    def _port_role(port: SourcePort) -> str:
        hints = {hint.lower() for hint in (port.port_hints or [])}
        if hints & {"out", "output", "source", "tx", "drive", "driver"}:
            return "output"
        if hints & {"in", "input", "sink", "rx", "load"}:
            return "input"
        return SourceToLayoutTransform._text_role(port.name)

    @staticmethod
    def _text_role(text: str | None) -> str:
        normalized = (text or "").lower()
        if normalized in {"out", "output", "tx"} or normalized.endswith("_out"):
            return "output"
        if normalized in {"in", "input", "rx"} or normalized.endswith("_in"):
            return "input"
        return "unknown"

    def _resize_group_nodes(self, node: LayoutNode) -> None:
        for child in node.children:
            self._resize_group_nodes(child)

        if not node.id.startswith("box_"):
            return

        child_count = len(node.children)
        if child_count:
            node.width = max(
                node.width,
                child_count * 40 + max(child_count - 1, 0) * 50 + LayoutSizingConfig.GROUP_PADDING * 2,
            )
            node.height = max(
                node.height,
                max((child.height for child in node.children), default=0)
                + LayoutSizingConfig.GROUP_PADDING * 2,
            )
        node.height = max(node.height, self._minimum_group_height(len(node.ports)))

    @staticmethod
    def _minimum_group_height(port_count: int) -> int:
        if port_count <= 0:
            return LayoutSizingConfig.MIN_BOX_HEIGHT
        per_edge_count = (port_count + 1) // 2
        return max(
            LayoutSizingConfig.MIN_BOX_HEIGHT,
            (per_edge_count + 1) * LayoutSizingConfig.PIN_SPACING,
        )

    def _add_connectivity(self, ctx: _TransformContext) -> None:
        """Add edges or labels based on crossing group boundaries."""
        sheet_conn = ctx.sheet_connectivity.get(ctx.sheet_id, [])
        component_to_group = self._build_comp_group_map(ctx)

        for conn in sorted(sheet_conn, key=lambda c: c.get("trace_id", "")):
            port_ids = sorted(conn.get("ports", []))
            if not port_ids:
                continue

            render_kind = conn.get("render_kind")
            if render_kind in {"local_label", "global_label", "hierarchical_label"}:
                self._add_labels(conn, port_ids, ctx)
                continue
            if render_kind == "wire":
                self._add_wires(conn, port_ids, ctx)
                continue

            # 1. Determine group membership for all ports in this trace
            port_groups = []
            for pid in port_ids:
                sport = next(
                    (
                        e
                        for e in ctx.elements
                        if isinstance(e, SourcePort) and e.source_port_id == pid
                    ),
                    None,
                )
                group = component_to_group.get(sport.source_component_id) if sport else None
                port_groups.append(group)

            # 2. Decide: Wires or Labels?
            # If all ports are in the same subgroup, use Wires.
            # If they span different subgroups, use Labels.
            is_cross_group = (
                len(set(port_groups)) > 1
                or conn.get("is_inter_sheet")
                or conn.get("is_global_net")
                or (len(port_ids) < 2 and conn.get("is_named_net"))
            )

            if not is_cross_group:
                self._add_wires(conn, port_ids, ctx)
            else:
                self._add_labels(conn, port_ids, ctx)

    def _build_comp_group_map(self, ctx: _TransformContext) -> dict[str, str]:
        """Maps component ID to its parent subgroup ID (if any)."""
        mapping = {}
        for comp in [e for e in ctx.elements if isinstance(e, SourceComponent)]:
            if comp.source_group_id:
                # Only map if it's a subgroup (on the same sheet)
                group = next(
                    (
                        g
                        for g in ctx.elements
                        if isinstance(g, SourceGroup) and g.source_group_id == comp.source_group_id
                    ),
                    None,
                )
                if group and not group.is_subcircuit:
                    mapping[comp.source_component_id] = comp.source_group_id
        return mapping

    def _add_wires(self, conn: dict[str, Any], port_ids: list[str], ctx: _TransformContext) -> None:
        """Connect ports with physical ELK edges."""
        src_elk_id = ctx.registry.element_to_port.get(port_ids[0])
        if not src_elk_id:
            return

        for target_port_id in port_ids[1:]:
            tgt_elk_id = ctx.registry.element_to_port.get(target_port_id)
            if tgt_elk_id:
                # Add edge to the lowest common ancestor node (usually root or subgroup box)
                ctx.root_node.edges.append(
                    LayoutEdge(
                        id=f"e_{conn['trace_id']}_{target_port_id}",
                        sources=[src_elk_id],
                        targets=[tgt_elk_id],
                    )
                )

    def _get_parent_node_for_elk_id(self, elk_id: str, ctx: _TransformContext) -> LayoutNode:
        """Find the LayoutNode that contains the given ELK ID (port or node)."""
        node_id = elk_id.split(":")[0] if ":" in elk_id else elk_id

        # Check if the node itself is in our map
        if node_id in ctx.node_map:
            return ctx.node_map[node_id]

        # If it's a component, find its parent group
        element = ctx.registry.get_element_by_layout_id(node_id)
        if isinstance(element, SourceComponent) and element.source_group_id:
            return ctx.node_map.get(f"box_{element.source_group_id}", ctx.root_node)

        return ctx.root_node

    def _add_labels(
        self, conn: dict[str, Any], port_ids: list[str], ctx: _TransformContext
    ) -> None:
        """Connect ports using local Net Labels instead of wires."""
        net_name = (
            conn.get("hier_label_text")
            if conn.get("render_kind") == "hierarchical_label"
            or (conn.get("is_inter_sheet") and not conn.get("is_global_net"))
            else conn.get("label_text")
        )
        net_name = net_name or f"NET_{conn['trace_id']}"

        for pid in port_ids:
            elk_port_id = ctx.registry.element_to_port.get(pid)
            if not elk_port_id:
                continue

            label_id = f"label_{conn['trace_id']}_{pid}"
            label_node = LayoutNode(id=f"label_node_{label_id}", width=len(net_name) * 7, height=10)

            # Place label node in the same parent as its component
            parent_node = self._get_parent_node_for_elk_id(elk_port_id, ctx)
            parent_node.children.append(label_node)

            # Create the visual element later during layout_to_schematic
            label_kwargs = {
                "sheet_id": ctx.sheet_id,
                "source_net_id": conn.get("net_id") or f"net_{conn['trace_id']}",
                "source_port_id": pid,
                "text": net_name,
                "center": Point(x=0, y=0),
            }
            if conn.get("is_inter_sheet") and not conn.get("is_global_net"):
                label_obj = SchematicHierarchicalLabel.model_construct(
                    schematic_hierarchical_label_id=label_id,
                    **label_kwargs,
                )
            else:
                label_obj = SchematicNetLabel.model_construct(
                    schematic_net_label_id=label_id,
                    is_global=bool(conn.get("is_global_net")),
                    **label_kwargs,
                )
            ctx.registry.register_node(label_obj, f"label_node_{label_id}")

            parent_node.edges.append(
                LayoutEdge(
                    id=f"e_label_{label_id}",
                    sources=[elk_port_id],
                    targets=[f"label_node_{label_id}"],
                )
            )

    def _add_hierarchical_edge(
        self, conn: dict[str, Any], port_id: str, ctx: _TransformContext
    ) -> None:
        """Draw an edge between a component port and a hierarchical pin on the root page."""
        src_elk_id = ctx.registry.element_to_port.get(port_id)
        hpin_elk_id = ctx.registry.element_to_port.get(conn["hpin_id"])

        if src_elk_id and hpin_elk_id:
            ctx.root_node.edges.append(
                LayoutEdge(
                    id=f"e_to_hpin_{conn['trace_id']}_{get_element_id(port_id)}",
                    sources=[src_elk_id],
                    targets=[hpin_elk_id],
                )
            )

    def _add_attachments(self, ctx: _TransformContext) -> None:
        """Add remaining visual attachments like no-connect markers."""
        for nc in [e for e in ctx.elements if isinstance(e, SchematicNoConnect)]:
            port_id = nc.schematic_port_id
            if port_id and port_id.startswith("port_"):
                port_id = port_id[5:]

            elk_port_id = ctx.registry.element_to_port.get(port_id)
            if not elk_port_id:
                continue

            nc_node_id = f"nc_node_{nc.schematic_no_connect_id}"
            parent_node = self._get_parent_node_for_elk_id(elk_port_id, ctx)

            nc_node = LayoutNode(id=nc_node_id, width=0, height=0)
            parent_node.children.append(nc_node)
            ctx.registry.register_node(nc, nc_node_id)

            parent_node.edges.append(
                LayoutEdge(
                    id=f"e_nc_{nc.schematic_no_connect_id}",
                    sources=[elk_port_id],
                    targets=[nc_node_id],
                )
            )

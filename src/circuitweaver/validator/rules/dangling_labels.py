"""Validation rule for dangling labels (labels not geometrically connected to their net)."""

import logging
from collections import defaultdict
from typing import Any, Dict, Set, Tuple

from circuitweaver.types.circuit_json import (
    CircuitElement,
    SchematicHierarchicalLabel,
    SchematicNetLabel,
    SchematicPort,
    SchematicHierarchicalPin,
    SchematicTrace,
    SourceTrace,
    SourcePort,
    get_element_id,
)
from circuitweaver.validator.result import ValidationResult
from circuitweaver.validator.rules.base import ValidationRule

logger = logging.getLogger(__name__)


class DanglingLabelsRule(ValidationRule):
    """Ensure all schematic labels are geometrically connected to a matching net.

    A label is considered connected if it shares a coordinate (center) with:
    1. A SchematicPort belonging to the same net.
    2. A SchematicHierarchicalPin belonging to the same net.
    3. An endpoint of a SchematicTrace belonging to the same net.
    """

    @property
    def name(self) -> str:
        return "dangling_labels"

    @property
    def description(self) -> str:
        return "All labels must be geometrically connected to a port, pin, or wire of the same net"

    def validate(
        self,
        elements: list[CircuitElement],
        context: dict[str, Any],
    ) -> ValidationResult:
        result = ValidationResult()

        # 1. Build Net mapping from Source data
        source_traces = {t.source_trace_id: t for t in elements if isinstance(t, SourceTrace)}
        
        # port_id -> set of net_ids
        port_to_nets = defaultdict(set)
        for t in source_traces.values():
            nid = t.connected_source_net_ids[0] if t.connected_source_net_ids else None
            if nid:
                for pid in t.connected_source_port_ids:
                    port_to_nets[pid].add(nid)

        # 2. Map coordinates to nets on each sheet
        # (sheet_id, x, y) -> set of net_ids
        net_at_point: Dict[Tuple[str, int, int], Set[str]] = defaultdict(set)
        
        def snap_coord(c): return (int(round(c.x)), int(round(c.y)))

        for e in elements:
            if isinstance(e, SchematicPort):
                nets = port_to_nets.get(e.source_port_id, set())
                net_at_point[(e.sheet_id, *snap_coord(e.center))].update(nets)
            
            elif isinstance(e, SchematicHierarchicalPin):
                net_at_point[(e.sheet_id, *snap_coord(e.center))].add(e.source_net_id)
            
            elif isinstance(e, SchematicTrace):
                nid = None
                if e.source_trace_id:
                    if e.source_trace_id in source_traces:
                        st = source_traces[e.source_trace_id]
                        nid = st.connected_source_net_ids[0] if st.connected_source_net_ids else e.source_trace_id
                    else:
                        nid = e.source_trace_id
                
                if nid:
                    for edge in e.edges:
                        net_at_point[(e.sheet_id, *snap_coord(edge.from_))].add(nid)
                        net_at_point[(e.sheet_id, *snap_coord(edge.to))].add(nid)

        # 3. Validate Labels
        for e in elements:
            if isinstance(e, (SchematicNetLabel, SchematicHierarchicalLabel)):
                # If it's at (0,0), it definitely wasn't positioned correctly
                if int(round(e.center.x)) == 0 and int(round(e.center.y)) == 0:
                    result.add_warning(
                        self.name,
                        f"Label '{e.text}' (Net: {e.source_net_id}) on sheet '{e.sheet_id}' is at (0,0). "
                        "It likely failed to match any pin for positioning.",
                        element_id=get_element_id(e)
                    )
                    continue

                point = (e.sheet_id, *snap_coord(e.center))
                nets_here = net_at_point.get(point, set())
                
                if e.source_net_id and e.source_net_id not in nets_here:
                    # Stricter check for positioned labels
                    result.add_warning(
                        self.name,
                        f"Label '{e.text}' (Net: {e.source_net_id}) on sheet '{e.sheet_id}' is at {snap_coord(e.center)} "
                        f"but no matching net connection found at this point. Nets here: {list(nets_here) or 'None'}",
                        element_id=get_element_id(e)
                    )

        return result

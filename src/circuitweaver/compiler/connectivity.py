"""Canonical source-connectivity planning.

This module keeps electrical net decisions in one place.  It intentionally
returns the legacy sheet-connectivity dictionaries for the current layout
pipeline, but the decisions are derived from typed, testable dataclasses first.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from circuitweaver.compiler.global_nets import GlobalNetResolver
from circuitweaver.types import (
    CircuitElement,
    Point,
    SchematicHierarchicalPin,
    SchematicNetLabel,
    SourceGroup,
    SourceNet,
    SourcePort,
    SourceTrace,
)
from circuitweaver.types.connectivity import RenderKind, SheetConnection


@dataclass(frozen=True)
class NetEndpoint:
    """One source port participating in a logical net."""

    port_id: str
    component_id: str
    sheet_id: str
    group_id: str | None


@dataclass(frozen=True)
class LogicalNet:
    """A canonical net built from one or more source traces."""

    net_id: str
    display_name: str
    source_trace_ids: tuple[str, ...]
    source_net_id: str | None
    endpoints: tuple[NetEndpoint, ...]
    is_global: bool



def build_logical_nets(
    *,
    traces: list[SourceTrace],
    ports: list[SourcePort],
    nets: list[SourceNet],
    element_to_sheet: dict[str, str],
    element_to_group: dict[str, str],
    global_resolver: GlobalNetResolver,
) -> list[LogicalNet]:
    """Build merged logical nets from source traces.

    All traces that reference the same first ``connected_source_net_ids`` entry
    are treated as the same electrical net.  Traces without a source net remain
    independent and use their trace ID as the net ID.
    """
    port_map = {p.source_port_id: p for p in ports}
    net_map = {n.source_net_id: n for n in nets}
    buckets: dict[str, dict[str, Any]] = {}

    for trace in traces:
        source_net_id = trace.connected_source_net_ids[0] if trace.connected_source_net_ids else None
        net_id = source_net_id or trace.source_trace_id
        source_net = net_map.get(source_net_id) if source_net_id else None
        display_name = source_net.name if source_net else (trace.display_name or trace.source_trace_id)
        bucket = buckets.setdefault(
            net_id,
            {
                "display_name": display_name,
                "source_net_id": source_net_id,
                "trace_ids": [],
                "endpoints": {},
                "source_net": source_net,
            },
        )
        bucket["trace_ids"].append(trace.source_trace_id)

        for port_id in trace.connected_source_port_ids:
            port = port_map.get(port_id)
            sheet_id = element_to_sheet.get(port_id)
            if port is None or sheet_id is None:
                continue
            bucket["endpoints"].setdefault(
                port_id,
                NetEndpoint(
                    port_id=port_id,
                    component_id=port.source_component_id,
                    sheet_id=sheet_id,
                    group_id=element_to_group.get(port.source_component_id),
                ),
            )

    logical_nets: list[LogicalNet] = []
    for net_id, bucket in buckets.items():
        source_net = bucket["source_net"]
        display_name = bucket["display_name"]
        logical_nets.append(
            LogicalNet(
                net_id=net_id,
                display_name=display_name,
                source_trace_ids=tuple(dict.fromkeys(bucket["trace_ids"])),
                source_net_id=bucket["source_net_id"],
                endpoints=tuple(bucket["endpoints"].values()),
                is_global=global_resolver.is_global(source_net, net_id, display_name),
            )
        )

    return logical_nets


def build_connection_plan(
    *,
    traces: list[SourceTrace],
    ports: list[SourcePort],
    nets: list[SourceNet],
    element_to_sheet: dict[str, str],
    element_to_group: dict[str, str],
    groups: list[SourceGroup],
    elements: list[CircuitElement],
    global_resolver: GlobalNetResolver,
) -> tuple[list[CircuitElement], dict[str, list[SheetConnection]]]:
    """Build generated hierarchy elements and typed per-sheet render decisions."""
    logical_nets = build_logical_nets(
        traces=traces,
        ports=ports,
        nets=nets,
        element_to_sheet=element_to_sheet,
        element_to_group=element_to_group,
        global_resolver=global_resolver,
    )

    generated: list[CircuitElement] = []
    sheet_connectivity: dict[str, list[SheetConnection]] = defaultdict(list)
    sheet_to_group = _sheet_to_group_id(groups)
    sheet_to_parent = _sheet_to_parent_sheet(groups, element_to_sheet)

    for logical_net in logical_nets:
        if not logical_net.endpoints:
            continue

        involved_sheets = sorted({endpoint.sheet_id for endpoint in logical_net.endpoints})
        is_inter_sheet = len(involved_sheets) > 1
        hierarchical_pin_by_sheet: dict[str, str] = {}
        hierarchical_text = f"HPIN_{logical_net.display_name}"

        connection_sheet = (
            _lowest_common_sheet(involved_sheets, sheet_to_parent)
            if is_inter_sheet
            else involved_sheets[0]
        )

        if is_inter_sheet and not logical_net.is_global:
            hierarchical_pin_by_sheet, bridge_connections = _build_hierarchical_elements(
                logical_net=logical_net,
                involved_sheets=involved_sheets,
                connection_sheet=connection_sheet,
                hierarchical_text=hierarchical_text,
                sheet_to_group=sheet_to_group,
                sheet_to_parent=sheet_to_parent,
                elements=elements,
                generated=generated,
            )
            for connection in bridge_connections:
                sheet_connectivity[connection.sheet_id].append(connection)

        for sheet_id in involved_sheets:
            endpoints = tuple(
                endpoint for endpoint in logical_net.endpoints if endpoint.sheet_id == sheet_id
            )
            groups_on_sheet = {endpoint.group_id or sheet_id for endpoint in endpoints}
            is_inter_group = len(groups_on_sheet) > 1
            render_kind = _render_kind_for_sheet(
                logical_net=logical_net,
                endpoint_count=len(endpoints),
                is_inter_sheet=is_inter_sheet,
                is_inter_group=is_inter_group,
                is_connection_sheet=sheet_id == connection_sheet,
            )
            label_text = (
                logical_net.display_name
                if render_kind == "global_label"
                else hierarchical_text
                if is_inter_sheet
                else f"NET_{logical_net.display_name}"
            )
            connection = SheetConnection(
                net_id=logical_net.net_id,
                trace_ids=logical_net.source_trace_ids,
                sheet_id=sheet_id,
                endpoint_port_ids=tuple(endpoint.port_id for endpoint in endpoints),
                render_kind=render_kind,
                label_text=label_text,
                hierarchical_label_text=hierarchical_text,
                source_net_id=logical_net.source_net_id,
                hierarchical_pin_id=hierarchical_pin_by_sheet.get(sheet_id),
                is_inter_group=is_inter_group,
                is_inter_sheet=is_inter_sheet,
            )
            sheet_connectivity[sheet_id].append(connection)

    return generated, sheet_connectivity


def build_sheet_connectivity(
    *,
    traces: list[SourceTrace],
    ports: list[SourcePort],
    nets: list[SourceNet],
    element_to_sheet: dict[str, str],
    element_to_group: dict[str, str],
    groups: list[SourceGroup],
    elements: list[CircuitElement],
    global_resolver: GlobalNetResolver,
) -> tuple[list[CircuitElement], dict[str, list[dict[str, Any]]]]:
    """Compatibility wrapper returning legacy sheet-connectivity dictionaries."""
    generated, plan = build_connection_plan(
        traces=traces,
        ports=ports,
        nets=nets,
        element_to_sheet=element_to_sheet,
        element_to_group=element_to_group,
        groups=groups,
        elements=elements,
        global_resolver=global_resolver,
    )
    return generated, {
        sheet_id: [connection.to_legacy_dict() for connection in connections]
        for sheet_id, connections in plan.items()
    }


def _render_kind_for_sheet(
    *,
    logical_net: LogicalNet,
    endpoint_count: int,
    is_inter_sheet: bool,
    is_inter_group: bool,
    is_connection_sheet: bool,
) -> RenderKind:
    if logical_net.is_global:
        return "global_label"
    if is_inter_sheet:
        return "local_label" if is_connection_sheet else "hierarchical_label"
    if is_inter_group:
        return "local_label"
    if endpoint_count < 2 and logical_net.source_net_id is not None:
        return "local_label"
    return "wire"


def _build_hierarchical_elements(
    *,
    logical_net: LogicalNet,
    involved_sheets: list[str],
    connection_sheet: str,
    hierarchical_text: str,
    sheet_to_group: dict[str, str],
    sheet_to_parent: dict[str, str],
    elements: list[CircuitElement],
    generated: list[CircuitElement],
) -> tuple[dict[str, str], list[SheetConnection]]:
    hierarchical_pin_by_sheet: dict[str, str] = {}
    bridge_connections: list[SheetConnection] = []
    involved_sheet_set = set(involved_sheets)

    for sheet_id in involved_sheets:
        if sheet_id == connection_sheet:
            continue

        current_sheet = sheet_id
        visited: set[str] = set()
        while current_sheet != connection_sheet:
            if current_sheet in visited:
                break
            visited.add(current_sheet)

            parent_sheet = _safe_parent_sheet(current_sheet, sheet_to_parent, visited)
            hpin_id = f"hpin_{logical_net.net_id}_{current_sheet}"
            if not _has_hierarchical_pin(elements + generated, hpin_id):
                generated.append(
                    SchematicHierarchicalPin(
                        schematic_hierarchical_pin_id=hpin_id,
                        sheet_id=parent_sheet,
                        source_net_id=logical_net.net_id,
                        schematic_box_id=f"box_{sheet_to_group.get(current_sheet, current_sheet)}",
                        center=Point(x=0, y=0),
                        text=hierarchical_text,
                    )
                )
                generated.append(
                    SchematicNetLabel(
                        schematic_net_label_id=f"root_label_{logical_net.net_id}_{current_sheet}",
                        sheet_id=parent_sheet,
                        source_net_id=logical_net.net_id,
                        schematic_hierarchical_pin_id=hpin_id,
                        center=Point(x=0, y=0),
                        text=hierarchical_text,
                    )
                )
            hierarchical_pin_by_sheet[current_sheet] = hpin_id
            hierarchical_pin_by_sheet[parent_sheet] = hpin_id

            if parent_sheet != connection_sheet and parent_sheet not in involved_sheet_set:
                bridge_connections.append(
                    SheetConnection(
                        net_id=logical_net.net_id,
                        trace_ids=logical_net.source_trace_ids,
                        sheet_id=parent_sheet,
                        endpoint_port_ids=(hpin_id,),
                        render_kind="hierarchical_label",
                        label_text=hierarchical_text,
                        hierarchical_label_text=hierarchical_text,
                        source_net_id=logical_net.source_net_id,
                        hierarchical_pin_id=hpin_id,
                        is_inter_sheet=True,
                    )
                )

            if parent_sheet == "root" and connection_sheet != "root":
                break
            current_sheet = parent_sheet

    return hierarchical_pin_by_sheet, bridge_connections


def _lowest_common_sheet(
    involved_sheets: list[str],
    sheet_to_parent: dict[str, str],
) -> str:
    if not involved_sheets:
        return "root"

    paths: list[tuple[str, ...]] = []
    for sheet_id in involved_sheets:
        path, has_cycle = _sheet_path_to_root(sheet_id, sheet_to_parent)
        if has_cycle:
            return "root"
        paths.append(path)

    common = set(paths[0])
    for path in paths[1:]:
        common.intersection_update(path)

    for sheet_id in paths[0]:
        if sheet_id in common:
            return sheet_id
    return "root"


def _sheet_path_to_root(
    sheet_id: str,
    sheet_to_parent: dict[str, str],
) -> tuple[tuple[str, ...], bool]:
    path: list[str] = []
    visited: set[str] = set()
    current_sheet = sheet_id
    has_cycle = False

    while True:
        if current_sheet in visited:
            has_cycle = True
            break

        path.append(current_sheet)
        if current_sheet == "root":
            break

        visited.add(current_sheet)
        parent_sheet = sheet_to_parent.get(current_sheet, "root")
        if parent_sheet == current_sheet:
            has_cycle = True
            break
        current_sheet = parent_sheet

    if path[-1] != "root":
        path.append("root")
    return tuple(path), has_cycle


def _safe_parent_sheet(
    current_sheet: str,
    sheet_to_parent: dict[str, str],
    visited: set[str],
) -> str:
    parent_sheet = sheet_to_parent.get(current_sheet, "root")
    if parent_sheet == current_sheet or parent_sheet in visited:
        return "root"
    return parent_sheet


def _sheet_to_group_id(groups: list[SourceGroup]) -> dict[str, str]:
    return {
        group.subcircuit_id or group.source_group_id: group.source_group_id
        for group in groups
        if group.is_subcircuit
    }


def _sheet_to_parent_sheet(
    groups: list[SourceGroup],
    element_to_sheet: dict[str, str],
) -> dict[str, str]:
    return {
        group.subcircuit_id or group.source_group_id: element_to_sheet.get(group.source_group_id, "root")
        for group in groups
        if group.is_subcircuit
    }


def _has_hierarchical_pin(elements: list[CircuitElement], hpin_id: str) -> bool:
    return any(
        isinstance(element, SchematicHierarchicalPin)
        and element.schematic_hierarchical_pin_id == hpin_id
        for element in elements
    )

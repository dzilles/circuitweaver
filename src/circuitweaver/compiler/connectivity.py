"""Canonical source-connectivity planning.

This module keeps electrical net decisions in one place.  It intentionally
returns the legacy sheet-connectivity dictionaries for the current layout
pipeline, but the decisions are derived from typed, testable dataclasses first.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Literal

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

RenderKind = Literal["wire", "local_label", "global_label", "hierarchical_label"]


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


@dataclass(frozen=True)
class SheetConnection:
    """How one logical net should be represented on one sheet."""

    net_id: str
    trace_ids: tuple[str, ...]
    sheet_id: str
    endpoint_port_ids: tuple[str, ...]
    render_kind: RenderKind
    label_text: str
    hierarchical_label_text: str
    hierarchical_pin_id: str | None = None
    is_inter_group: bool = False
    is_inter_sheet: bool = False

    def to_legacy_dict(self) -> dict[str, Any]:
        """Return the current dictionary shape consumed by layout code."""
        return {
            "trace_id": self.trace_ids[0] if self.trace_ids else self.net_id,
            "trace_ids": list(self.trace_ids),
            "net_id": self.net_id,
            "ports": list(self.endpoint_port_ids),
            "is_inter_group": self.is_inter_group,
            "is_inter_sheet": self.is_inter_sheet,
            "is_global_net": self.render_kind == "global_label",
            "label_text": self.label_text,
            "hier_label_text": self.hierarchical_label_text,
            "hpin_id": self.hierarchical_pin_id,
            "render_kind": self.render_kind,
        }


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
    """Build generated hierarchy elements and per-sheet render decisions."""
    logical_nets = build_logical_nets(
        traces=traces,
        ports=ports,
        nets=nets,
        element_to_sheet=element_to_sheet,
        element_to_group=element_to_group,
        global_resolver=global_resolver,
    )

    generated: list[CircuitElement] = []
    sheet_connectivity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    sheet_to_group = _sheet_to_group_id(groups)
    sheet_to_parent = _sheet_to_parent_sheet(groups, element_to_sheet)

    for logical_net in logical_nets:
        if not logical_net.endpoints:
            continue

        involved_sheets = sorted({endpoint.sheet_id for endpoint in logical_net.endpoints})
        is_inter_sheet = len(involved_sheets) > 1
        hierarchical_pin_by_sheet: dict[str, str] = {}
        hierarchical_text = f"HPIN_{logical_net.display_name}"

        if is_inter_sheet and not logical_net.is_global:
            hierarchical_pin_by_sheet = _build_hierarchical_elements(
                logical_net=logical_net,
                involved_sheets=involved_sheets,
                hierarchical_text=hierarchical_text,
                sheet_to_group=sheet_to_group,
                sheet_to_parent=sheet_to_parent,
                elements=elements,
                generated=generated,
            )

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
            )
            label_text = (
                logical_net.display_name
                if render_kind == "global_label"
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
                hierarchical_pin_id=hierarchical_pin_by_sheet.get(sheet_id),
                is_inter_group=is_inter_group,
                is_inter_sheet=is_inter_sheet,
            )
            legacy = connection.to_legacy_dict()
            legacy["is_named_net"] = logical_net.source_net_id is not None
            sheet_connectivity[sheet_id].append(legacy)

    return generated, sheet_connectivity


def _render_kind_for_sheet(
    *,
    logical_net: LogicalNet,
    endpoint_count: int,
    is_inter_sheet: bool,
    is_inter_group: bool,
) -> RenderKind:
    if logical_net.is_global:
        return "global_label"
    if is_inter_sheet:
        return "hierarchical_label"
    if is_inter_group:
        return "local_label"
    if endpoint_count < 2 and logical_net.source_net_id is not None:
        return "local_label"
    return "wire"


def _build_hierarchical_elements(
    *,
    logical_net: LogicalNet,
    involved_sheets: list[str],
    hierarchical_text: str,
    sheet_to_group: dict[str, str],
    sheet_to_parent: dict[str, str],
    elements: list[CircuitElement],
    generated: list[CircuitElement],
) -> dict[str, str]:
    hierarchical_pin_by_sheet: dict[str, str] = {}

    for sheet_id in involved_sheets:
        if sheet_id == "root":
            continue

        current_sheet = sheet_id
        while current_sheet != "root":
            parent_sheet = sheet_to_parent.get(current_sheet, "root")
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
            current_sheet = parent_sheet

    return hierarchical_pin_by_sheet


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

"""Layout quality checks for generated schematic elements."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from circuitweaver.transform.source_to_layout import get_effective_symbol_id
from circuitweaver.types import (
    CircuitElement,
    SchematicBox,
    SchematicComponent,
    SchematicHierarchicalLabel,
    SchematicHierarchicalPin,
    SchematicNetLabel,
    SchematicPort,
    SchematicTrace,
    SourceComponent,
    SourceGroup,
    get_element_id,
)


@dataclass(frozen=True)
class Bounds:
    """Axis-aligned bounds in schematic grid units."""

    x1: float
    y1: float
    x2: float
    y2: float

    def intersects(self, other: Bounds) -> bool:
        return (
            self.x1 < other.x2 and self.x2 > other.x1 and self.y1 < other.y2 and self.y2 > other.y1
        )

    def contains(self, other: Bounds, padding: float = 0) -> bool:
        return (
            self.x1 + padding <= other.x1
            and self.y1 + padding <= other.y1
            and self.x2 - padding >= other.x2
            and self.y2 - padding >= other.y2
        )

    def as_dict(self) -> dict[str, float]:
        return {"x1": self.x1, "y1": self.y1, "x2": self.x2, "y2": self.y2}


@dataclass(frozen=True)
class LayoutQualityDiagnostic:
    """A single layout-quality issue."""

    rule: str
    message: str
    sheet_id: str
    element_ids: tuple[str, ...]
    severity: str = "warning"
    bounds: tuple[Bounds, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "rule": self.rule,
            "message": self.message,
            "sheet_id": self.sheet_id,
            "element_ids": list(self.element_ids),
            "severity": self.severity,
            "bounds": [b.as_dict() for b in self.bounds],
        }

    def __str__(self) -> str:
        ids = ", ".join(self.element_ids)
        return f"[{self.rule}] ({self.sheet_id}) {ids}: {self.message}"


@dataclass
class LayoutQualityReport:
    """Result from layout-quality checking."""

    diagnostics: list[LayoutQualityDiagnostic] = field(default_factory=list)

    @property
    def warning_count(self) -> int:
        return sum(1 for d in self.diagnostics if d.severity == "warning")

    @property
    def error_count(self) -> int:
        return sum(1 for d in self.diagnostics if d.severity == "error")

    @property
    def is_valid(self) -> bool:
        return self.error_count == 0

    def add(self, diagnostic: LayoutQualityDiagnostic) -> None:
        self.diagnostics.append(diagnostic)

    def to_dict(self) -> dict[str, object]:
        return {
            "is_valid": self.is_valid,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "diagnostic_count": len(self.diagnostics),
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }


class LayoutQualityChecker:
    """Checks simple, measurable schematic layout-quality rules."""

    def __init__(
        self,
        symbol_map: dict[str, object] | None = None,
        component_fallback_size: float = 40,
        label_char_width: float = 7,
        label_height: float = 10,
    ) -> None:
        self.symbol_map = symbol_map or {}
        self.component_fallback_size = component_fallback_size
        self.label_char_width = label_char_width
        self.label_height = label_height

    def check(self, elements: Iterable[CircuitElement]) -> LayoutQualityReport:
        items = list(elements)
        report = LayoutQualityReport()

        components = [e for e in items if isinstance(e, SchematicComponent)]
        labels = [
            e for e in items if isinstance(e, (SchematicNetLabel, SchematicHierarchicalLabel))
        ]
        boxes = [e for e in items if isinstance(e, SchematicBox)]
        hpins = [e for e in items if isinstance(e, SchematicHierarchicalPin)]
        ports = [e for e in items if isinstance(e, SchematicPort)]
        traces = [e for e in items if isinstance(e, SchematicTrace)]
        source_components = {
            e.source_component_id: e for e in items if isinstance(e, SourceComponent)
        }
        source_groups = {e.source_group_id: e for e in items if isinstance(e, SourceGroup)}

        component_bounds = {
            c.schematic_component_id: self._component_bounds(c, source_components)
            for c in components
        }
        label_bounds = {get_element_id(label): self._label_bounds(label) for label in labels}
        box_bounds = {b.schematic_box_id: self._box_bounds(b) for b in boxes}

        self._check_component_overlaps(report, components, component_bounds)
        self._check_label_zero_positions(report, labels)
        component_sheets = {c.schematic_component_id: c.sheet_id for c in components}
        self._check_label_overlaps(report, labels, label_bounds, component_bounds, component_sheets)
        self._check_root_sheet_box_overlaps(report, boxes, box_bounds)
        self._check_hierarchical_pin_overlaps(report, hpins)
        self._check_hierarchical_pin_boundaries(report, hpins, box_bounds)
        self._check_sheet_box_pin_capacity(report, boxes, hpins, box_bounds)
        self._check_label_reference_proximity(report, labels, ports, hpins)
        self._check_trace_quality(report, traces, components, component_bounds)
        self._check_component_group_containment(
            report, components, component_bounds, boxes, box_bounds, source_components
        )
        self._check_child_sheet_ownership(
            report, components, source_components, source_groups
        )

        return report

    def _component_bounds(
        self,
        comp: SchematicComponent,
        sources: dict[str, SourceComponent],
    ) -> Bounds:
        source = sources.get(comp.source_component_id)
        symbol = None
        if source:
            symbol_id = get_effective_symbol_id(source)
            symbol = self.symbol_map.get(symbol_id) if symbol_id else None

        width = getattr(symbol, "width", self.component_fallback_size)
        height = getattr(symbol, "height", self.component_fallback_size)
        return Bounds(
            comp.center.x - width / 2,
            comp.center.y - height / 2,
            comp.center.x + width / 2,
            comp.center.y + height / 2,
        )

    def _label_bounds(
        self,
        label: SchematicNetLabel | SchematicHierarchicalLabel,
    ) -> Bounds:
        width = max(len(label.text), 1) * self.label_char_width
        height = self.label_height
        return Bounds(
            label.center.x - width / 2,
            label.center.y - height / 2,
            label.center.x + width / 2,
            label.center.y + height / 2,
        )

    def _box_bounds(self, box: SchematicBox) -> Bounds:
        return Bounds(box.x, box.y, box.x + box.width, box.y + box.height)

    def _check_component_overlaps(
        self,
        report: LayoutQualityReport,
        components: list[SchematicComponent],
        bounds: dict[str, Bounds],
    ) -> None:
        for i, a in enumerate(components):
            for b in components[i + 1 :]:
                if a.sheet_id != b.sheet_id:
                    continue
                a_bounds = bounds[a.schematic_component_id]
                b_bounds = bounds[b.schematic_component_id]
                if a_bounds.intersects(b_bounds):
                    report.add(
                        LayoutQualityDiagnostic(
                            rule="LQ-040",
                            message="Generated component bounding boxes overlap.",
                            sheet_id=a.sheet_id,
                            element_ids=(a.schematic_component_id, b.schematic_component_id),
                            bounds=(a_bounds, b_bounds),
                        )
                    )

    def _check_label_zero_positions(
        self,
        report: LayoutQualityReport,
        labels: list[SchematicNetLabel | SchematicHierarchicalLabel],
    ) -> None:
        for label in labels:
            if label.center.x == 0 and label.center.y == 0:
                report.add(
                    LayoutQualityDiagnostic(
                        rule="LQ-102",
                        message="Generated label remains at (0, 0).",
                        sheet_id=label.sheet_id,
                        element_ids=(get_element_id(label),),
                        bounds=(self._label_bounds(label),),
                    )
                )

    def _check_label_overlaps(
        self,
        report: LayoutQualityReport,
        labels: list[SchematicNetLabel | SchematicHierarchicalLabel],
        label_bounds: dict[str, Bounds],
        component_bounds: dict[str, Bounds],
        component_sheets: dict[str, str],
    ) -> None:
        # Labels shall not overlap component bodies.
        for label in labels:
            label_id = get_element_id(label)
            for comp_id, comp_bounds in component_bounds.items():
                if component_sheets.get(comp_id) != label.sheet_id:
                    continue
                lbl_bounds = label_bounds[label_id]
                if lbl_bounds.intersects(comp_bounds):
                    report.add(
                        LayoutQualityDiagnostic(
                            rule="LQ-041",
                            message="Generated label overlaps a component bounding box.",
                            sheet_id=label.sheet_id,
                            element_ids=(label_id, comp_id),
                            bounds=(lbl_bounds, comp_bounds),
                        )
                    )

        # Labels shall not overlap other labels.
        for i, a in enumerate(labels):
            a_id = get_element_id(a)
            for b in labels[i + 1 :]:
                if a.sheet_id != b.sheet_id:
                    continue
                b_id = get_element_id(b)
                a_bounds = label_bounds[a_id]
                b_bounds = label_bounds[b_id]
                if a_bounds.intersects(b_bounds):
                    report.add(
                        LayoutQualityDiagnostic(
                            rule="LQ-042",
                            message="Generated labels overlap.",
                            sheet_id=a.sheet_id,
                            element_ids=(a_id, b_id),
                            bounds=(a_bounds, b_bounds),
                        )
                    )

    def _check_root_sheet_box_overlaps(
        self,
        report: LayoutQualityReport,
        boxes: list[SchematicBox],
        bounds: dict[str, Bounds],
    ) -> None:
        root_boxes = [b for b in boxes if b.sheet_id == "root" and b.is_hierarchical_sheet]
        for i, a in enumerate(root_boxes):
            for b in root_boxes[i + 1 :]:
                a_bounds = bounds[a.schematic_box_id]
                b_bounds = bounds[b.schematic_box_id]
                if a_bounds.intersects(b_bounds):
                    report.add(
                        LayoutQualityDiagnostic(
                            rule="LQ-104",
                            message="Root-page sheet boxes overlap.",
                            sheet_id="root",
                            element_ids=(a.schematic_box_id, b.schematic_box_id),
                            bounds=(a_bounds, b_bounds),
                        )
                    )

    def _check_hierarchical_pin_overlaps(
        self,
        report: LayoutQualityReport,
        hpins: list[SchematicHierarchicalPin],
    ) -> None:
        by_box: dict[tuple[str, str], list[SchematicHierarchicalPin]] = {}
        for hpin in hpins:
            by_box.setdefault((hpin.sheet_id, hpin.schematic_box_id), []).append(hpin)

        for (sheet_id, _box_id), pins in by_box.items():
            seen: dict[tuple[float, float], SchematicHierarchicalPin] = {}
            for pin in pins:
                key = (pin.center.x, pin.center.y)
                if key in seen:
                    other = seen[key]
                    report.add(
                        LayoutQualityDiagnostic(
                            rule="LQ-043",
                            message="Hierarchical pins overlap on the same sheet box.",
                            sheet_id=sheet_id,
                            element_ids=(
                                other.schematic_hierarchical_pin_id,
                                pin.schematic_hierarchical_pin_id,
                            ),
                        )
                    )
                else:
                    seen[key] = pin

    def _check_component_group_containment(
        self,
        report: LayoutQualityReport,
        components: list[SchematicComponent],
        component_bounds: dict[str, Bounds],
        boxes: list[SchematicBox],
        box_bounds: dict[str, Bounds],
        sources: dict[str, SourceComponent],
    ) -> None:
        boxes_by_id = {box.schematic_box_id: box for box in boxes}
        for comp in components:
            source = sources.get(comp.source_component_id)
            if not source or not source.source_group_id:
                continue
            box_id = f"box_{source.source_group_id}"
            box = boxes_by_id.get(box_id)
            if not box or box.sheet_id != comp.sheet_id:
                continue
            comp_bounds = component_bounds[comp.schematic_component_id]
            parent_bounds = box_bounds[box.schematic_box_id]
            if not parent_bounds.contains(comp_bounds):
                report.add(
                    LayoutQualityDiagnostic(
                        rule="LQ-103",
                        message="Component is outside its assigned group box.",
                        sheet_id=comp.sheet_id,
                        element_ids=(comp.schematic_component_id, box.schematic_box_id),
                        bounds=(comp_bounds, parent_bounds),
                    )
                )

    def _check_child_sheet_ownership(
        self,
        report: LayoutQualityReport,
        components: list[SchematicComponent],
        sources: dict[str, SourceComponent],
        groups: dict[str, SourceGroup],
    ) -> None:
        for comp in components:
            source = sources.get(comp.source_component_id)
            if not source:
                continue
            expected_sheet = None
            if source.source_group_id:
                group = groups.get(source.source_group_id)
                if group and group.is_subcircuit:
                    expected_sheet = group.subcircuit_id or group.source_group_id
            if source.subcircuit_id:
                expected_sheet = source.subcircuit_id
            if expected_sheet and comp.sheet_id != expected_sheet:
                report.add(
                    LayoutQualityDiagnostic(
                        rule="LQ-103",
                        message="Component is not on its assigned child sheet.",
                        sheet_id=comp.sheet_id,
                        element_ids=(comp.schematic_component_id, expected_sheet),
                    )
                )

    def _check_hierarchical_pin_boundaries(
        self,
        report: LayoutQualityReport,
        hpins: list[SchematicHierarchicalPin],
        box_bounds: dict[str, Bounds],
    ) -> None:
        for pin in hpins:
            box = box_bounds.get(pin.schematic_box_id)
            if box is None:
                continue
            on_vertical = pin.center.x in {box.x1, box.x2} and box.y1 <= pin.center.y <= box.y2
            on_horizontal = pin.center.y in {box.y1, box.y2} and box.x1 <= pin.center.x <= box.x2
            if not on_vertical and not on_horizontal:
                report.add(
                    LayoutQualityDiagnostic(
                        rule="LQ-023",
                        message="Hierarchical pin is not on its sheet box boundary.",
                        sheet_id=pin.sheet_id,
                        element_ids=(pin.schematic_hierarchical_pin_id, pin.schematic_box_id),
                        bounds=(box,),
                    )
                )

    def _check_sheet_box_pin_capacity(
        self,
        report: LayoutQualityReport,
        boxes: list[SchematicBox],
        hpins: list[SchematicHierarchicalPin],
        box_bounds: dict[str, Bounds],
    ) -> None:
        pins_by_box: dict[str, list[SchematicHierarchicalPin]] = {}
        for pin in hpins:
            pins_by_box.setdefault(pin.schematic_box_id, []).append(pin)

        for box in boxes:
            pins = pins_by_box.get(box.schematic_box_id, [])
            if not box.is_hierarchical_sheet or not pins:
                continue
            per_edge = (len(pins) + 1) // 2
            required_height = max(60, (per_edge + 1) * 20)
            field_clearance = 30
            if box.height < required_height + field_clearance:
                report.add(
                    LayoutQualityDiagnostic(
                        rule="LQ-024",
                        message="Sheet box is too small for hierarchical pins and sheet fields.",
                        sheet_id=box.sheet_id,
                        element_ids=(box.schematic_box_id, *tuple(p.schematic_hierarchical_pin_id for p in pins)),
                        bounds=(box_bounds[box.schematic_box_id],),
                    )
                )

    def _check_label_reference_proximity(
        self,
        report: LayoutQualityReport,
        labels: list[SchematicNetLabel | SchematicHierarchicalLabel],
        ports: list[SchematicPort],
        hpins: list[SchematicHierarchicalPin],
    ) -> None:
        ports_by_id = {port.source_port_id: port for port in ports}
        hpins_by_id = {pin.schematic_hierarchical_pin_id: pin for pin in hpins}
        max_distance = 40

        for label in labels:
            label_id = get_element_id(label)
            if label.source_port_id and label.source_port_id in ports_by_id:
                port = ports_by_id[label.source_port_id]
                if label.sheet_id == port.sheet_id and self._distance(label.center, port.center) > max_distance:
                    report.add(
                        LayoutQualityDiagnostic(
                            rule="LQ-060",
                            message="Generated label is not near its referenced component port.",
                            sheet_id=label.sheet_id,
                            element_ids=(label_id, port.schematic_port_id),
                        )
                    )
            if isinstance(label, SchematicNetLabel) and label.schematic_hierarchical_pin_id:
                pin = hpins_by_id.get(label.schematic_hierarchical_pin_id)
                if pin and label.sheet_id == pin.sheet_id and self._distance(label.center, pin.center) > max_distance:
                    report.add(
                        LayoutQualityDiagnostic(
                            rule="LQ-063",
                            message="Root-page label is not near its referenced hierarchical sheet pin.",
                            sheet_id=label.sheet_id,
                            element_ids=(label_id, pin.schematic_hierarchical_pin_id),
                        )
                    )

    def _check_trace_quality(
        self,
        report: LayoutQualityReport,
        traces: list[SchematicTrace],
        components: list[SchematicComponent],
        component_bounds: dict[str, Bounds],
    ) -> None:
        component_sheets = {comp.schematic_component_id: comp.sheet_id for comp in components}
        for trace in traces:
            for edge in trace.edges:
                start = edge.from_
                end = edge.to
                if start.x != end.x and start.y != end.y:
                    report.add(
                        LayoutQualityDiagnostic(
                            rule="LQ-080",
                            message="Generated wire segment is not orthogonal.",
                            sheet_id=trace.sheet_id,
                            element_ids=(trace.schematic_trace_id,),
                        )
                    )
                for comp_id, bounds in component_bounds.items():
                    if component_sheets.get(comp_id) != trace.sheet_id:
                        continue
                    if self._segment_intersects_bounds(start, end, bounds):
                        report.add(
                            LayoutQualityDiagnostic(
                                rule="LQ-081",
                                message="Generated wire segment routes through a component bounding box.",
                                sheet_id=trace.sheet_id,
                                element_ids=(trace.schematic_trace_id, comp_id),
                                bounds=(bounds,),
                            )
                        )

    @staticmethod
    def _distance(a, b) -> float:
        return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5

    @staticmethod
    def _segment_intersects_bounds(start, end, bounds: Bounds) -> bool:
        if start.x == end.x:
            x = start.x
            y1, y2 = sorted((start.y, end.y))
            return bounds.x1 < x < bounds.x2 and y1 < bounds.y2 and y2 > bounds.y1
        if start.y == end.y:
            y = start.y
            x1, x2 = sorted((start.x, end.x))
            return bounds.y1 < y < bounds.y2 and x1 < bounds.x2 and x2 > bounds.x1

        segment_bounds = Bounds(
            min(start.x, end.x),
            min(start.y, end.y),
            max(start.x, end.x),
            max(start.y, end.y),
        )
        return segment_bounds.intersects(bounds)

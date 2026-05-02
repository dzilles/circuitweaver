"""First-class CircuitWeaver project container."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from circuitweaver.types import (
    CircuitElement,
    SExpr,
    SourceComponent,
    SourceGroup,
    SourceNet,
    SourcePort,
    SourceTrace,
)


@dataclass
class CircuitProject:
    """Typed container for a CircuitWeaver design and generated artifacts."""

    elements: list[CircuitElement] = field(default_factory=list)
    name: str = "project"
    source_path: Path | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    layout_artifacts: dict[str, object] = field(default_factory=dict)

    @property
    def source_elements(self) -> list[CircuitElement]:
        return [e for e in self.elements if e.type.startswith("source_")]

    @property
    def schematic_elements(self) -> list[CircuitElement]:
        return [e for e in self.elements if e.type.startswith("schematic_")]

    @property
    def source_components(self) -> dict[str, SourceComponent]:
        return {e.source_component_id: e for e in self.elements if isinstance(e, SourceComponent)}

    @property
    def source_ports(self) -> dict[str, SourcePort]:
        return {e.source_port_id: e for e in self.elements if isinstance(e, SourcePort)}

    @property
    def source_nets(self) -> dict[str, SourceNet]:
        return {e.source_net_id: e for e in self.elements if isinstance(e, SourceNet)}

    @property
    def source_traces(self) -> dict[str, SourceTrace]:
        return {e.source_trace_id: e for e in self.elements if isinstance(e, SourceTrace)}

    @property
    def source_groups(self) -> dict[str, SourceGroup]:
        return {e.source_group_id: e for e in self.elements if isinstance(e, SourceGroup)}

    @property
    def sheet_ids(self) -> set[str]:
        sheets = {e.sheet_id for e in self.schematic_elements if hasattr(e, "sheet_id")}
        return sheets or {"root"}

    def with_elements(self, elements: list[CircuitElement]) -> "CircuitProject":
        return CircuitProject(
            elements=elements,
            name=self.name,
            source_path=self.source_path,
            metadata=dict(self.metadata),
            layout_artifacts=dict(self.layout_artifacts),
        )

    def has_schematic_layer(self) -> bool:
        return bool(self.schematic_elements)


@dataclass
class KiCadProject:
    """In-memory KiCad output generated from a CircuitProject."""

    project: CircuitProject
    schematics: dict[str, SExpr]
    project_file_content: str

    @property
    def root_schematic_sheet_id(self) -> str:
        return "root"

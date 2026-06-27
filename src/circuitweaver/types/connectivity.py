"""Shared typed connectivity render-plan models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

RenderKind = Literal["wire", "local_label", "global_label", "hierarchical_label"]


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
    source_net_id: str | None = None
    hierarchical_pin_id: str | None = None
    is_inter_group: bool = False
    is_inter_sheet: bool = False

    @property
    def trace_id(self) -> str:
        """Return the primary trace ID used for stable generated layout IDs."""
        return self.trace_ids[0] if self.trace_ids else self.net_id

    @property
    def is_global_net(self) -> bool:
        """Return whether this connection should render as a global KiCad label."""
        return self.render_kind == "global_label"

    def to_legacy_dict(self) -> dict[str, Any]:
        """Return the dictionary shape used by compatibility callers."""
        return {
            "trace_id": self.trace_id,
            "trace_ids": list(self.trace_ids),
            "net_id": self.net_id,
            "ports": list(self.endpoint_port_ids),
            "is_inter_group": self.is_inter_group,
            "is_inter_sheet": self.is_inter_sheet,
            "is_global_net": self.is_global_net,
            "is_named_net": self.source_net_id is not None,
            "label_text": self.label_text,
            "hier_label_text": self.hierarchical_label_text,
            "hpin_id": self.hierarchical_pin_id,
            "render_kind": self.render_kind,
        }

"""Shared structured result types for pipeline and tool operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Diagnostic:
    """Structured error or warning reported by a stage or tool."""

    severity: str
    code: str
    message: str
    element_id: str | None = None
    location: dict[str, object] | None = None
    stage: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "element_id": self.element_id,
            "location": self.location,
            "stage": self.stage,
        }


@dataclass(frozen=True)
class OutputArtifact:
    """A file or in-memory artifact created by a stage or tool."""

    kind: str
    path: Path | None = None
    name: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "path": str(self.path) if self.path else None,
            "name": self.name,
            "metadata": self.metadata,
        }


@dataclass
class StageResult(Generic[T]):
    """Result from one compiler pipeline stage."""

    stage: str
    value: T | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    artifacts: list[OutputArtifact] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(d.severity == "error" for d in self.diagnostics)

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "error"]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "warning"]

    def add_error(
        self,
        code: str,
        message: str,
        element_id: str | None = None,
        location: dict[str, object] | None = None,
    ) -> None:
        self.diagnostics.append(
            Diagnostic(
                severity="error",
                code=code,
                message=message,
                element_id=element_id,
                location=location,
                stage=self.stage,
            )
        )

    def add_warning(
        self,
        code: str,
        message: str,
        element_id: str | None = None,
        location: dict[str, object] | None = None,
    ) -> None:
        self.diagnostics.append(
            Diagnostic(
                severity="warning",
                code=code,
                message=message,
                element_id=element_id,
                location=location,
                stage=self.stage,
            )
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "stage": self.stage,
            "ok": self.ok,
            "errors": [d.to_dict() for d in self.errors],
            "warnings": [d.to_dict() for d in self.warnings],
            "artifacts": [a.to_dict() for a in self.artifacts],
        }


@dataclass
class ToolResult:
    """Structured result shape for MCP and CLI-facing operations."""

    ok: bool
    summary: str = ""
    errors: list[Diagnostic] = field(default_factory=list)
    warnings: list[Diagnostic] = field(default_factory=list)
    outputs: list[OutputArtifact] = field(default_factory=list)
    data: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        payload = {
            "ok": self.ok,
            "summary": self.summary,
            "errors": [d.to_dict() for d in self.errors],
            "warnings": [d.to_dict() for d in self.warnings],
            "outputs": [o.to_dict() for o in self.outputs],
        }
        payload.update(self.data)
        return payload

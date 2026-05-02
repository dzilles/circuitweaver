"""Unified ERC runner for CLI, MCP, and Python callers."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from circuitweaver.erc.checker import ERCChecker
from circuitweaver.io.json import read_circuit
from circuitweaver.results import Diagnostic, OutputArtifact, ToolResult


def _erc_result_payload(raw: dict[str, Any]) -> dict[str, object]:
    return {
        "is_valid": bool(raw.get("is_valid", False)),
        "errors": list(raw.get("errors", [])),
        "warnings": list(raw.get("warnings", [])),
        "total_violations": raw.get(
            "total_violations",
            len(raw.get("errors", [])) + len(raw.get("warnings", [])),
        ),
    }


def _diagnostics(messages: list[str], severity: str) -> list[Diagnostic]:
    return [
        Diagnostic(
            severity=severity,
            code="erc_violation" if severity == "error" else "erc_warning",
            message=message,
            stage="erc",
        )
        for message in messages
    ]


def _result_from_raw(
    raw: dict[str, Any],
    summary_target: Path,
    outputs: list[OutputArtifact],
) -> ToolResult:
    payload = _erc_result_payload(raw)
    errors = _diagnostics(payload["errors"], "error")
    warnings = _diagnostics(payload["warnings"], "warning")
    ok = bool(payload["is_valid"])
    summary = (
        f"ERC passed for {summary_target}"
        if ok
        else f"ERC found {len(errors)} error(s) for {summary_target}"
    )
    return ToolResult(
        ok=ok,
        summary=summary,
        errors=errors,
        warnings=warnings,
        outputs=outputs,
        data={"erc": payload},
    )


def _run_existing_schematic(path: Path) -> ToolResult:
    raw = ERCChecker().run(path)
    return _result_from_raw(
        raw,
        path,
        [OutputArtifact(kind="erc_input_schematic", path=path, name=path.name)],
    )


def _run_circuit_json(
    path: Path,
    output_dir: Path | None,
    project_name: str | None,
    keep_generated: bool,
) -> ToolResult:
    name = project_name or path.stem
    elements = read_circuit(path)
    from circuitweaver.compiler.engine import CompileEngine

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        engine = CompileEngine()
        root_schematic = engine.compile(elements, output_dir, project_name=name)
        raw = engine.run_erc(root_schematic)
        return _result_from_raw(
            raw,
            path,
            [
                OutputArtifact(kind="erc_input_json", path=path, name=path.name),
                OutputArtifact(
                    kind="erc_generated_schematic",
                    path=root_schematic,
                    name=root_schematic.name,
                    metadata={"temporary": False},
                ),
            ],
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        engine = CompileEngine()
        root_schematic = engine.compile(elements, tmp_path, project_name=name)
        raw = engine.run_erc(root_schematic)
        outputs = [
            OutputArtifact(kind="erc_input_json", path=path, name=path.name),
            OutputArtifact(
                kind="erc_generated_schematic",
                path=root_schematic,
                name=root_schematic.name,
                metadata={"temporary": not keep_generated},
            ),
        ]
        return _result_from_raw(raw, path, outputs)


def run_erc_for_path(
    file_path: str | Path,
    output_dir: str | Path | None = None,
    project_name: str | None = None,
    keep_generated: bool = False,
) -> ToolResult:
    """Run ERC for either Circuit JSON input or an existing KiCad schematic."""
    path = Path(file_path)
    if not path.exists():
        return ToolResult(
            ok=False,
            summary=f"File not found: {path}",
            errors=[
                Diagnostic(
                    severity="error",
                    code="file_not_found",
                    message=f"File not found: {path}",
                    location={"path": str(path)},
                    stage="erc",
                )
            ],
            data={"erc": {"is_valid": False, "errors": [f"File not found: {path}"], "warnings": []}},
        )
    if not path.is_file():
        return ToolResult(
            ok=False,
            summary=f"Not a file: {path}",
            errors=[
                Diagnostic(
                    severity="error",
                    code="not_a_file",
                    message=f"Not a file: {path}",
                    location={"path": str(path)},
                    stage="erc",
                )
            ],
            data={"erc": {"is_valid": False, "errors": [f"Not a file: {path}"], "warnings": []}},
        )

    resolved_output_dir = Path(output_dir) if output_dir is not None else None
    if path.suffix == ".kicad_sch":
        return _run_existing_schematic(path)
    if path.suffix == ".json":
        return _run_circuit_json(path, resolved_output_dir, project_name, keep_generated)

    return ToolResult(
        ok=False,
        summary=f"Unsupported ERC input type: {path}",
        errors=[
            Diagnostic(
                severity="error",
                code="unsupported_input_type",
                message="ERC input must be a Circuit JSON file or a .kicad_sch schematic.",
                location={"path": str(path)},
                stage="erc",
            )
        ],
        data={"erc": {"is_valid": False, "errors": ["Unsupported ERC input type"], "warnings": []}},
    )

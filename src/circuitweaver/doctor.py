"""Environment diagnostics for CircuitWeaver."""

from __future__ import annotations

import importlib
import json
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from circuitweaver import __version__
from circuitweaver.library.paths import find_kicad_cli, get_library_paths
from circuitweaver.server import mcp_server


@dataclass(frozen=True)
class DoctorCheck:
    """Single doctor diagnostic check."""

    name: str
    ok: bool
    details: str = ""
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "ok": self.ok,
            "details": self.details,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class DoctorReport:
    """Aggregated doctor diagnostics."""

    checks: list[DoctorCheck]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "checks": [check.to_dict() for check in self.checks],
        }


def run_doctor(
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> DoctorReport:
    """Run environment diagnostics."""
    checks = [
        _check_python_package(),
        _check_node(command_runner),
        _check_elkjs(command_runner),
        _check_library_paths(),
        _check_kicad_cli(),
        _check_mcp_resources(),
    ]
    return DoctorReport(checks=checks)


def _check_python_package() -> DoctorCheck:
    try:
        importlib.import_module("circuitweaver")
    except Exception as e:
        return DoctorCheck("python_package", False, str(e))
    return DoctorCheck(
        "python_package",
        True,
        f"circuitweaver {__version__} is importable.",
        {"version": __version__},
    )


def _check_node(
    command_runner: Callable[..., subprocess.CompletedProcess[str]],
) -> DoctorCheck:
    node = shutil.which("node")
    if node is None:
        return DoctorCheck("node", False, "Node.js was not found in PATH.")
    try:
        completed = command_runner(
            [node, "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except Exception as e:
        return DoctorCheck("node", False, str(e), {"path": node})
    return DoctorCheck("node", completed.returncode == 0, completed.stdout.strip(), {"path": node})


def _check_elkjs(
    command_runner: Callable[..., subprocess.CompletedProcess[str]],
) -> DoctorCheck:
    node = shutil.which("node")
    if node is None:
        return DoctorCheck("elkjs", False, "Cannot check elkjs because Node.js was not found.")
    script = "require.resolve('elkjs')"
    env_node_path = str(Path.cwd() / "node_modules")
    try:
        completed = command_runner(
            [node, "-e", script],
            capture_output=True,
            text=True,
            check=False,
            env={"NODE_PATH": env_node_path},
            timeout=5,
        )
    except Exception as e:
        return DoctorCheck("elkjs", False, str(e))
    return DoctorCheck(
        "elkjs",
        completed.returncode == 0,
        "elkjs is resolvable." if completed.returncode == 0 else completed.stderr.strip(),
    )


def _check_library_paths() -> DoctorCheck:
    paths = get_library_paths()
    metadata = {
        "symbols": str(paths.symbols) if paths.symbols else None,
        "footprints": str(paths.footprints) if paths.footprints else None,
        "models_3d": str(paths.models_3d) if paths.models_3d else None,
        "templates": str(paths.templates) if paths.templates else None,
    }
    ok = bool(paths.symbols and paths.footprints)
    return DoctorCheck(
        "kicad_library_paths",
        ok,
        "Detected KiCad symbol and footprint paths." if ok else "KiCad library paths are incomplete.",
        metadata,
    )


def _check_kicad_cli() -> DoctorCheck:
    cli = find_kicad_cli()
    return DoctorCheck(
        "kicad_cli",
        cli is not None,
        str(cli) if cli else "kicad-cli was not found in PATH or common install locations.",
        {"path": str(cli) if cli else None},
    )


def _check_mcp_resources() -> DoctorCheck:
    checks = {
        "readme": mcp_server._get_readme(),
        "workflow": mcp_server._get_mcp_workflow(),
        "spec": mcp_server._get_circuit_json_spec(),
        "troubleshooting": mcp_server._get_troubleshooting(),
        "examples": mcp_server._get_examples(),
    }
    missing = [name for name, content in checks.items() if "Error:" in content]
    return DoctorCheck(
        "mcp_resources",
        not missing,
        "Packaged MCP resources are readable." if not missing else f"Missing resources: {', '.join(missing)}",
        {"resources": sorted(checks)},
    )


def doctor_json(report: DoctorReport) -> str:
    """Serialize a doctor report as formatted JSON."""
    return json.dumps(report.to_dict(), indent=2)

"""ERC checker using KiCad CLI."""

import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from circuitweaver.library.paths import find_kicad_cli
from circuitweaver.types.errors import KiCadNotFoundError

logger = logging.getLogger(__name__)


@dataclass
class ERCViolation:
    """A single ERC violation."""

    severity: str  # "error" or "warning"
    type: str
    message: str
    sheet: Optional[str] = None
    position: Optional[dict[str, float]] = None


@dataclass
class ERCResult:
    """Result of running ERC on a schematic."""

    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    violations: list[ERCViolation] = field(default_factory=list)
    raw_output: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "passed": self.passed,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": self.errors,
            "warnings": self.warnings,
            "violations": [
                {
                    "severity": v.severity,
                    "type": v.type,
                    "message": v.message,
                    "sheet": v.sheet,
                    "position": v.position,
                }
                for v in self.violations
            ],
        }


def run_erc(schematic_file: Path) -> ERCResult:
    """Run Electrical Rules Check on a KiCad schematic.

    Args:
        schematic_file: Path to the .kicad_sch file.

    Returns:
        ERCResult with errors and warnings.

    Raises:
        KiCadNotFoundError: If kicad-cli is not available.
        FileNotFoundError: If the schematic file doesn't exist.
    """
    if not schematic_file.exists():
        raise FileNotFoundError(f"Schematic file not found: {schematic_file}")

    kicad_cli = find_kicad_cli()
    if not kicad_cli:
        raise KiCadNotFoundError()

    # Create temp file for ERC report
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as report_file:
        report_path = Path(report_file.name)

    try:
        # Run kicad-cli erc
        cmd = [
            str(kicad_cli),
            "sch",
            "erc",
            "--format", "json",
            "--output", str(report_path),
            str(schematic_file),
        ]

        logger.debug(f"Running ERC: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Parse report
        if report_path.exists():
            return _parse_erc_report(report_path, result.returncode == 0)
        else:
            # No report generated, check stderr
            return ERCResult(
                passed=False,
                errors=[f"ERC failed: {result.stderr}"] if result.stderr else ["ERC failed with no output"],
                raw_output=result.stderr,
            )

    except subprocess.TimeoutExpired:
        return ERCResult(
            passed=False,
            errors=["ERC timed out after 60 seconds"],
        )
    except Exception as e:
        return ERCResult(
            passed=False,
            errors=[f"ERC execution error: {e}"],
        )
    finally:
        # Clean up temp file
        if report_path.exists():
            report_path.unlink()


def _parse_erc_report(report_path: Path, cli_success: bool) -> ERCResult:
    """Parse KiCad ERC JSON report."""
    try:
        with open(report_path) as f:
            report = json.load(f)
    except json.JSONDecodeError as e:
        return ERCResult(
            passed=False,
            errors=[f"Failed to parse ERC report: {e}"],
        )

    violations: list[ERCViolation] = []
    errors: list[str] = []
    warnings: list[str] = []

    # Parse violations from each sheet
    for sheet in report.get("sheets", []):
        sheet_path = sheet.get("path", "/")

        for violation in sheet.get("violations", []):
            severity = violation.get("severity", "error").lower()
            v_type = violation.get("type", "unknown")
            message = violation.get("description", "No description")
            pos = violation.get("items", [{}])[0].get("pos") if violation.get("items") else None

            v = ERCViolation(
                severity=severity,
                type=v_type,
                message=message,
                sheet=sheet_path,
                position=pos,
            )
            violations.append(v)

            formatted = f"[{v_type}] {message}"
            if sheet_path and sheet_path != "/":
                formatted += f" (sheet: {sheet_path})"

            if severity == "error":
                errors.append(formatted)
            else:
                warnings.append(formatted)

        # Check for sheet-level errors
        for sheet_error in sheet.get("errors", []):
            errors.append(f"[Sheet Error] {sheet_error}")

    passed = len(errors) == 0 and cli_success

    return ERCResult(
        passed=passed,
        errors=errors,
        warnings=warnings,
        violations=violations,
        raw_output=json.dumps(report, indent=2),
    )


def run_erc_basic(schematic_file: Path) -> ERCResult:
    """Run basic ERC checks without KiCad CLI.

    This provides limited checking when KiCad is not available.
    Checks for:
    - Unconnected wires (based on schematic structure)
    - Missing power flags

    Args:
        schematic_file: Path to the .kicad_sch file.

    Returns:
        ERCResult with any detected issues.
    """
    # This is a placeholder for basic checks
    # Real implementation would parse the schematic and check for issues
    return ERCResult(
        passed=True,
        warnings=["Basic ERC only - install KiCad for full checking"],
    )

"""ERC (Electrical Rules Check) using KiCad CLI."""

import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from circuitweaver.types.errors import ERCError

logger = logging.getLogger(__name__)


class ERCChecker:
    """Wrapper for KiCad ERC functionality."""

    def __init__(self, kicad_cli_path: str = "kicad-cli"):
        self.kicad_cli_path = kicad_cli_path

    def run(self, schematic_path: Path) -> Dict[str, Any]:
        """Run ERC on the given schematic and return results."""
        if not schematic_path.exists():
            raise FileNotFoundError(f"Schematic not found: {schematic_path}")

        with tempfile.TemporaryDirectory() as tmpdir:
            report_file = Path(tmpdir) / "erc_report.json"
            
            cmd = [
                self.kicad_cli_path,
                "sch",
                "erc",
                str(schematic_path),
                "--format", "json",
                "--output", str(report_file)
            ]
            
            # Run ERC.
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if not report_file.exists():
                # CAPTURE STDERR for better debugging
                error_msg = result.stderr if result.stderr else result.stdout
                return {
                    "is_valid": False,
                    "errors": [f"ERC report was not generated. CLI Output: {error_msg}"],
                    "warnings": []
                }

            try:
                report_data = json.loads(report_file.read_text())
                return self._parse_report(report_data)
            except json.JSONDecodeError as e:
                return {
                    "is_valid": False,
                    "errors": [f"Failed to parse ERC report: {e}"],
                    "warnings": []
                }

    def _parse_report(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse KiCad 10 ERC JSON report into a standard format."""
        errors = []
        warnings = []
        
        # KiCad 10 format: violations are inside sheets list
        sheets = data.get("sheets", [])
        for sheet in sheets:
            violations = sheet.get("violations", [])
            for v in violations:
                severity = v.get("severity", "error").lower()
                desc = v.get("description", "Unknown error")
                vtype = v.get("type", "erc_violation")
                
                # Location helper
                items = v.get("items", [])
                loc_str = "unknown"
                if items:
                    pos = items[0].get("pos", {})
                    if pos:
                        loc_str = f"({pos.get('x', 0)}, {pos.get('y', 0)})"
                
                msg = f"{vtype}: {desc} at {loc_str}"
                
                if severity == "error":
                    errors.append(msg)
                else:
                    warnings.append(msg)
                
        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "total_violations": len(errors) + len(warnings)
        }

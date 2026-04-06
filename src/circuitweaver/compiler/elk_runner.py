import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ElkRunner:
    """
    Handles the execution of the ELK layout engine via a Node.js subprocess.
    """

    def __init__(self, helper_path: Optional[Path] = None):
        """
        Initializes the ElkRunner and verifies the Node.js dependency.

        Args:
            helper_path: Path to the layout_helper.js file. Defaults to the same directory as this file.

        Raises:
            RuntimeError: If Node.js is not found in the system PATH.
        """
        if not shutil.which("node"):
            raise RuntimeError(
                "Node.js is required for schematic auto-layout but was not found in PATH."
            )

        if helper_path:
            self.helper_path = helper_path
        else:
            self.helper_path = Path(__file__).parent / "layout_helper.js"

        if not self.helper_path.exists():
            raise RuntimeError(f"ELK layout helper not found at: {self.helper_path}")

    def run(self, graph: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pipes the ELK graph JSON to the Node.js process and returns the parsed layout results.

        Args:
            graph: A dictionary representing the ELK graph.

        Returns:
            The layout data returned by ELK as a dictionary.

        Raises:
            RuntimeError: If the Node.js process fails or returns an error.
        """
        try:
            process = subprocess.run(
                ["node", str(self.helper_path)],
                input=json.dumps(graph),
                capture_output=True,
                text=True,
                check=True,
            )
            return json.loads(process.stdout)
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else e.stdout
            logger.error(f"ELK Layout subprocess failed: {error_msg}")
            raise RuntimeError(f"ELK Layout failed: {error_msg}") from e
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse ELK output as JSON: {e}")
            raise RuntimeError("Invalid JSON output from ELK layout helper.") from e

"""Auto-routing via ELK layout engine.

Handles execution of the ELK (Eclipse Layout Kernel) via Node.js subprocess.
"""

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AutoRouter:
    """Executes the ELK layout engine via Node.js subprocess.

    ELK (Eclipse Layout Kernel) computes positions for nodes and routes
    edges between them.
    """

    def __init__(self, helper_path: Path | None = None):
        """Initialize the auto-router.

        Args:
            helper_path: Path to the layout_helper.js file.
                        Defaults to the same directory as this file.

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

    def run(self, graph: dict[str, Any]) -> dict[str, Any]:
        """Execute the ELK layout algorithm on a graph.

        Args:
            graph: A dictionary representing the ELK graph (nodes, ports, edges).

        Returns:
            The layout data returned by ELK with computed positions.

        Raises:
            RuntimeError: If the Node.js process fails or returns an error.
        """
        try:
            env = os.environ.copy()
            node_paths = [
                str(Path.cwd() / "node_modules"),
                str(self.helper_path.parent.parent.parent.parent / "node_modules"),
            ]
            existing_node_path = env.get("NODE_PATH")
            if existing_node_path:
                node_paths.append(existing_node_path)
            env["NODE_PATH"] = os.pathsep.join(node_paths)

            process = subprocess.run(
                ["node", str(self.helper_path)],
                input=json.dumps(graph),
                capture_output=True,
                text=True,
                check=True,
                env=env,
            )
            return json.loads(process.stdout)
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else e.stdout
            logger.error(f"ELK Layout subprocess failed: {error_msg}")
            raise RuntimeError(f"ELK Layout failed: {error_msg}") from e
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse ELK output as JSON: {e}")
            raise RuntimeError("Invalid JSON output from ELK layout helper.") from e

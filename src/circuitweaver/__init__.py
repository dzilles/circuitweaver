"""CircuitWeaver - Circuit JSON netlist tools for AI-assisted electronic design."""

__version__ = "0.2.0"
__author__ = "CircuitWeaver Contributors"

from circuitweaver.project import CircuitProject, KiCadProject
from circuitweaver.results import Diagnostic, OutputArtifact, StageResult, ToolResult
from circuitweaver.types import (
    CircuitElement,
    SourceComponent,
    SourceGroup,
    SourceNet,
    SourcePort,
    SourceTrace,
)

__all__ = [
    "__version__",
    # Project and result types
    "CircuitProject",
    "KiCadProject",
    "Diagnostic",
    "OutputArtifact",
    "StageResult",
    "ToolResult",
    # Source types
    "SourceComponent",
    "SourcePort",
    "SourceNet",
    "SourceTrace",
    "SourceGroup",
    # Union type
    "CircuitElement",
]

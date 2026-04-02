"""CircuitWeaver - Circuit JSON netlist tools for AI-assisted electronic design."""

__version__ = "0.2.0"
__author__ = "CircuitWeaver Contributors"

from circuitweaver.types.circuit_json import (
    CircuitElement,
    SourceComponent,
    SourceGroup,
    SourceNet,
    SourcePort,
    SourceTrace,
)

__all__ = [
    "__version__",
    # Source types
    "SourceComponent",
    "SourcePort",
    "SourceNet",
    "SourceTrace",
    "SourceGroup",
    # Union type
    "CircuitElement",
]

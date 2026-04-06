from abc import ABC, abstractmethod
from typing import Any, Dict, List
from circuitweaver.types.circuit_json import CircuitElement
from ..registry import LayoutContext

class LayoutPlugin(ABC):
    """Base interface for schematic layout plugins."""
    
    @abstractmethod
    def build(self, context: LayoutContext) -> None:
        """Add nodes/edges to the context.root_node."""
        pass

    @abstractmethod
    def apply(self, context: LayoutContext, results: Dict[str, Any]) -> List[CircuitElement]:
        """Convert layout results back to CircuitElements."""
        pass

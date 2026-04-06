"""KiCad library interface for CircuitWeaver."""

from circuitweaver.library.search import PartInfo, search_parts
from circuitweaver.library.pinout import Pin, SymbolInfo, get_symbol_info, get_symbol_pinout
from circuitweaver.types.circuit_json import GridOffset, Point
from circuitweaver.library.paths import LibraryPaths, get_library_paths

__all__ = [
    "search_parts",
    "PartInfo",
    "get_symbol_pinout",
    "get_symbol_info",
    "SymbolInfo",
    "Pin",
    "get_library_paths",
    "LibraryPaths",
]


def __getattr__(name: str):
    """Provide deprecation warning for PinInfo alias."""
    if name == "PinInfo":
        import warnings
        warnings.warn(
            "PinInfo is deprecated, use Pin instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return Pin
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

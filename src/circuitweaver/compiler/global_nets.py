"""Global net resolution for hierarchical compilation."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from circuitweaver.library.paths import get_library_paths
from circuitweaver.types import CircuitElement, SourceNet, SourceProjectConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GlobalNetResolver:
    """Resolves whether a source net should be emitted as a global net."""

    global_names: frozenset[str]

    @classmethod
    def from_elements(cls, elements: list[CircuitElement]) -> GlobalNetResolver:
        config = next((e for e in elements if isinstance(e, SourceProjectConfig)), None)
        use_kicad_defaults = (
            config.use_kicad_power_symbols_as_global_nets if config else True
        )

        names: set[str] = set(config.global_net_names if config else [])
        if use_kicad_defaults:
            names.update(get_kicad_power_symbol_global_names())

        for net in (e for e in elements if isinstance(e, SourceNet)):
            if net.is_global or net.is_power or net.is_ground:
                names.add(net.source_net_id)
                names.add(net.name)

        return cls(frozenset(_normalize_name(name) for name in names if name))

    def is_global(self, net: SourceNet | None, net_id: str, net_name: str) -> bool:
        candidates = {net_id, net_name}
        if net:
            candidates.update({net.source_net_id, net.name})
        return any(_normalize_name(candidate) in self.global_names for candidate in candidates)


@lru_cache(maxsize=1)
def get_kicad_power_symbol_global_names() -> frozenset[str]:
    """Extract default global names from KiCad's power symbol library."""
    lib_paths = get_library_paths()
    if not lib_paths.symbols:
        logger.warning("KiCad symbol path not found; power symbol globals unavailable")
        return frozenset()

    power_lib = Path(lib_paths.symbols) / "power.kicad_sym"
    if not power_lib.exists():
        logger.warning("KiCad power symbol library not found: %s", power_lib)
        return frozenset()

    content = power_lib.read_text(encoding="utf-8", errors="replace")
    names: set[str] = set()
    for match in re.finditer(r'\(symbol\s+"([^"]+)"', content):
        name = match.group(1)
        if re.search(r"_\d+_\d+$", name):
            continue
        names.add(name)
        if name.startswith("+"):
            names.add(name[1:])

    return frozenset(_normalize_name(name) for name in names)


def _normalize_name(name: str) -> str:
    return name.strip().upper()

"""KiCad part search functionality."""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from circuitweaver.library.paths import get_library_paths

logger = logging.getLogger(__name__)


@dataclass
class PartInfo:
    """Information about a KiCad part."""

    library_id: str  # e.g., "Device:R"
    library_name: str  # e.g., "Device"
    symbol_name: str  # e.g., "R"
    description: Optional[str] = None
    keywords: Optional[str] = None
    default_footprint: Optional[str] = None
    datasheet: Optional[str] = None


# Built-in common parts for when KiCad is not installed
BUILTIN_PARTS: list[PartInfo] = [
    PartInfo(
        library_id="Device:R",
        library_name="Device",
        symbol_name="R",
        description="Resistor",
        keywords="resistor res r",
        default_footprint="Resistor_SMD:R_0603_1608Metric",
    ),
    PartInfo(
        library_id="Device:R_Small",
        library_name="Device",
        symbol_name="R_Small",
        description="Resistor (small symbol)",
        keywords="resistor res r small",
        default_footprint="Resistor_SMD:R_0402_1005Metric",
    ),
    PartInfo(
        library_id="Device:C",
        library_name="Device",
        symbol_name="C",
        description="Unpolarized capacitor",
        keywords="capacitor cap c",
        default_footprint="Capacitor_SMD:C_0603_1608Metric",
    ),
    PartInfo(
        library_id="Device:C_Polarized",
        library_name="Device",
        symbol_name="C_Polarized",
        description="Polarized capacitor",
        keywords="capacitor cap c polarized electrolytic",
        default_footprint="Capacitor_SMD:C_0805_2012Metric",
    ),
    PartInfo(
        library_id="Device:L",
        library_name="Device",
        symbol_name="L",
        description="Inductor",
        keywords="inductor coil choke l",
        default_footprint="Inductor_SMD:L_0603_1608Metric",
    ),
    PartInfo(
        library_id="Device:LED",
        library_name="Device",
        symbol_name="LED",
        description="Light Emitting Diode",
        keywords="led diode light",
        default_footprint="LED_SMD:LED_0603_1608Metric",
    ),
    PartInfo(
        library_id="Device:D",
        library_name="Device",
        symbol_name="D",
        description="Diode",
        keywords="diode d",
        default_footprint="Diode_SMD:D_SOD-123",
    ),
    PartInfo(
        library_id="Device:D_Schottky",
        library_name="Device",
        symbol_name="D_Schottky",
        description="Schottky diode",
        keywords="diode schottky",
        default_footprint="Diode_SMD:D_SOD-123",
    ),
    PartInfo(
        library_id="Device:D_Zener",
        library_name="Device",
        symbol_name="D_Zener",
        description="Zener diode",
        keywords="diode zener",
        default_footprint="Diode_SMD:D_SOD-123",
    ),
    PartInfo(
        library_id="Device:Q_NPN_BCE",
        library_name="Device",
        symbol_name="Q_NPN_BCE",
        description="NPN transistor (BCE pinout)",
        keywords="transistor npn bjt",
        default_footprint="Package_TO_SOT_SMD:SOT-23",
    ),
    PartInfo(
        library_id="Device:Q_PNP_BCE",
        library_name="Device",
        symbol_name="Q_PNP_BCE",
        description="PNP transistor (BCE pinout)",
        keywords="transistor pnp bjt",
        default_footprint="Package_TO_SOT_SMD:SOT-23",
    ),
    PartInfo(
        library_id="Device:Q_NMOS_GDS",
        library_name="Device",
        symbol_name="Q_NMOS_GDS",
        description="N-channel MOSFET (GDS pinout)",
        keywords="transistor nmos mosfet n-channel",
        default_footprint="Package_TO_SOT_SMD:SOT-23",
    ),
    PartInfo(
        library_id="Device:Q_PMOS_GDS",
        library_name="Device",
        symbol_name="Q_PMOS_GDS",
        description="P-channel MOSFET (GDS pinout)",
        keywords="transistor pmos mosfet p-channel",
        default_footprint="Package_TO_SOT_SMD:SOT-23",
    ),
    PartInfo(
        library_id="Device:Crystal",
        library_name="Device",
        symbol_name="Crystal",
        description="Crystal oscillator",
        keywords="crystal quartz oscillator xtal",
        default_footprint="Crystal:Crystal_SMD_3215-2Pin",
    ),
    PartInfo(
        library_id="Device:Fuse",
        library_name="Device",
        symbol_name="Fuse",
        description="Fuse",
        keywords="fuse protection",
        default_footprint="Fuse:Fuse_0603_1608Metric",
    ),
    PartInfo(
        library_id="Power:GND",
        library_name="Power",
        symbol_name="GND",
        description="Ground power symbol",
        keywords="power ground gnd",
    ),
    PartInfo(
        library_id="Power:+3V3",
        library_name="Power",
        symbol_name="+3V3",
        description="3.3V power symbol",
        keywords="power 3.3v 3v3",
    ),
    PartInfo(
        library_id="Power:+5V",
        library_name="Power",
        symbol_name="+5V",
        description="5V power symbol",
        keywords="power 5v",
    ),
    PartInfo(
        library_id="Power:VCC",
        library_name="Power",
        symbol_name="VCC",
        description="VCC power symbol",
        keywords="power vcc",
    ),
    PartInfo(
        library_id="Power:PWR_FLAG",
        library_name="Power",
        symbol_name="PWR_FLAG",
        description="Power flag for ERC",
        keywords="power flag erc",
    ),
    PartInfo(
        library_id="Connector:Conn_01x02_Pin",
        library_name="Connector",
        symbol_name="Conn_01x02_Pin",
        description="2-pin connector",
        keywords="connector header pin",
        default_footprint="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
    ),
    PartInfo(
        library_id="Connector:Conn_01x04_Pin",
        library_name="Connector",
        symbol_name="Conn_01x04_Pin",
        description="4-pin connector",
        keywords="connector header pin",
        default_footprint="Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
    ),
]


def search_parts(query: str, limit: int = 10) -> list[PartInfo]:
    """Search for KiCad parts matching a query.

    Searches both built-in parts and installed KiCad libraries.

    Args:
        query: Search query (case-insensitive).
        limit: Maximum number of results.

    Returns:
        List of matching PartInfo objects.
    """
    results: list[PartInfo] = []
    query_lower = query.lower()
    query_words = query_lower.split()

    # Search built-in parts first
    for part in BUILTIN_PARTS:
        if _matches_query(part, query_words):
            results.append(part)
            if len(results) >= limit:
                return results

    # Search installed KiCad libraries
    lib_paths = get_library_paths()
    if lib_paths.symbols:
        lib_results = _search_kicad_libraries(lib_paths.symbols, query_words, limit - len(results))
        results.extend(lib_results)

    return results[:limit]


def _matches_query(part: PartInfo, query_words: list[str]) -> bool:
    """Check if a part matches the query words."""
    searchable = " ".join(
        filter(
            None,
            [
                part.library_id.lower(),
                part.symbol_name.lower(),
                (part.description or "").lower(),
                (part.keywords or "").lower(),
            ],
        )
    )

    return all(word in searchable for word in query_words)


def _search_kicad_libraries(
    symbols_path: Path, query_words: list[str], limit: int
) -> list[PartInfo]:
    """Search KiCad symbol libraries on disk."""
    results: list[PartInfo] = []

    if not symbols_path.exists():
        return results

    # Find all .kicad_sym files
    for sym_file in symbols_path.glob("*.kicad_sym"):
        if len(results) >= limit:
            break

        library_name = sym_file.stem
        try:
            parts = _parse_symbol_library(sym_file, query_words, limit - len(results))
            results.extend(parts)
        except Exception as e:
            logger.warning(f"Error parsing {sym_file}: {e}")

    return results


def _parse_symbol_library(
    sym_file: Path, query_words: list[str], limit: int
) -> list[PartInfo]:
    """Parse a KiCad symbol library file and extract matching symbols.
    
    This is optimized to avoid character-by-character S-expression parsing
    unless a match is found.
    """
    results: list[PartInfo] = []
    library_name = sym_file.stem

    content = sym_file.read_text(errors="replace")

    # Pattern to find symbols and their properties in a single pass if possible
    # We find all (symbol "Name" blocks
    symbol_pattern = re.compile(r'\(symbol\s+"([^"]+)"')
    
    # We'll split the file by (symbol to quickly process chunks
    chunks = symbol_pattern.split(content)
    # chunks[0] is everything before the first (symbol
    # chunks[1] is name of first symbol
    # chunks[2] is content of first symbol (until next (symbol)
    
    for i in range(1, len(chunks), 2):
        if len(results) >= limit:
            break

        symbol_name = chunks[i]
        symbol_content = chunks[i+1]

        # Skip sub-units (e.g., "Symbol_1_1")
        if "_" in symbol_name and symbol_name.split("_")[-1].isdigit():
            continue

        library_id = f"{library_name}:{symbol_name}"

        # Fast check: does the ID/Name match?
        id_match = all(word in library_id.lower() or word in symbol_name.lower() for word in query_words)
        
        # Extract properties only if we need to check them for a match OR if we have an ID match
        # We search within the chunk (which is everything between (symbol "NAME" and the next (symbol)
        
        # Description
        desc_match = re.search(r'\(property\s+"Description"\s+"([^"]*)"', symbol_content)
        description = desc_match.group(1) if desc_match else None
        
        # Keywords
        key_match = re.search(r'\(property\s+"Keywords"\s+"([^"]*)"', symbol_content)
        keywords = key_match.group(1) if key_match else None
        
        # If no ID match, check if properties match
        if not id_match:
            searchable = " ".join(filter(None, [description, keywords])).lower()
            if not all(word in searchable for word in query_words):
                continue

        # Footprint (for result display)
        fp_match = re.search(r'\(property\s+"Footprint"\s+"([^"]*)"', symbol_content)
        default_footprint = fp_match.group(1) if fp_match else None

        results.append(PartInfo(
            library_id=library_id,
            library_name=library_name,
            symbol_name=symbol_name,
            description=description,
            keywords=keywords,
            default_footprint=default_footprint,
        ))

    return results

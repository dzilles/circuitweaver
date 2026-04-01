"""Symbol pinout extraction for KiCad symbols."""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from circuitweaver.library.paths import get_library_paths

logger = logging.getLogger(__name__)


@dataclass
class GridOffset:
    """Pin offset from component center in grid units.

    1 grid unit = 0.127mm (5mil) for fine precision.
    """

    x: int
    y: int


@dataclass
class PinInfo:
    """Information about a symbol pin."""

    number: str
    name: str
    grid_offset: GridOffset
    direction: str  # "up", "down", "left", "right"
    electrical_type: str  # "input", "output", "passive", "power_in", etc.


def _find_library_file(lib_paths, library_name: str) -> Path:
    """Find a library file by name, trying case-insensitive match if needed."""
    if not lib_paths.symbols:
        raise ValueError("KiCad symbol libraries not found.")
        
    # Try exact match first
    lib_file = lib_paths.symbols / f"{library_name}.kicad_sym"
    if lib_file.exists():
        return lib_file
        
    # Try lowercase match (common on Linux)
    lib_file = lib_paths.symbols / f"{library_name.lower()}.kicad_sym"
    if lib_file.exists():
        return lib_file
        
    # List available to help user
    available_libs = [f.stem for f in lib_paths.symbols.glob("*.kicad_sym")][:10]
    raise ValueError(
        f"Symbol library '{library_name}' not found. "
        f"Available libraries include: {', '.join(available_libs)}..."
    )


def get_symbol_pinout(symbol_id: str) -> list[PinInfo]:
    """Get pin positions for a KiCad symbol in grid units.

    Parses the actual KiCad symbol library to extract pin information.
    All coordinates are returned in integer grid units (1 unit = 2.54mm).

    Args:
        symbol_id: Symbol identifier in "Library:Symbol" format (e.g., "Device:R").

    Returns:
        List of PinInfo with pin positions in grid units.

    Raises:
        ValueError: If symbol_id format is invalid, library not found, or symbol not found.
    """
    # Validate format
    if ":" not in symbol_id:
        raise ValueError(
            f"Invalid symbol_id format: '{symbol_id}'. "
            f"Expected 'Library:Symbol' format (e.g., 'Device:R', 'Device:LED')."
        )

    library_name, symbol_name = symbol_id.split(":", 1)

    # Get library paths
    lib_paths = get_library_paths()
    lib_file = _find_library_file(lib_paths, library_name)

    # Parse the library and find the symbol
    return _parse_symbol_from_library(lib_file, symbol_name, symbol_id)


def _parse_symbol_from_library(
    lib_file: Path, symbol_name: str, symbol_id: str
) -> list[PinInfo]:
    """Parse a KiCad symbol library file and extract pin information."""
    content = lib_file.read_text(errors="replace")

    # Find the symbol definition
    symbol_start = _find_symbol_start(content, symbol_name)
    if symbol_start == -1:
        # Try to find similar symbols for helpful error
        available = _find_available_symbols(content, limit=10)
        raise ValueError(
            f"Symbol '{symbol_name}' not found in library '{lib_file.stem}'. "
            f"Available symbols include: {', '.join(available)}. "
            f"Use 'circuitweaver search <query>' to find symbols."
        )

    # Extract the full symbol definition
    symbol_content = _extract_balanced_sexp(content, symbol_start)

    # Check if this symbol extends another symbol
    extends_match = re.search(r'\(extends\s+"([^"]+)"\)', symbol_content)
    if extends_match:
        base_symbol_name = extends_match.group(1)
        # Recursively find pins from the base symbol in the same library
        try:
            return _parse_symbol_from_library(lib_file, base_symbol_name, f"{lib_file.stem}:{base_symbol_name}")
        except ValueError as e:
            # If base symbol not found in same library, it might be a cross-library extend
            # but usually they are in the same library.
            raise ValueError(f"Symbol '{symbol_id}' extends '{base_symbol_name}', but base symbol could not be parsed: {e}")

    # Parse pins from the symbol
    pins = _extract_pins(symbol_content)

    if not pins:
        raise ValueError(
            f"Symbol '{symbol_id}' has no pins defined. "
            f"This may be a power symbol or graphical element."
        )

    return pins


def _find_symbol_start(content: str, symbol_name: str) -> int:
    """Find the start position of a symbol definition."""
    # Look for (symbol "SymbolName" at top level (not sub-units like "R_0_1")
    pattern = rf'\(symbol\s+"{re.escape(symbol_name)}"(?:\s|\n)'
    match = re.search(pattern, content)
    if match:
        return match.start()
    return -1


def _extract_balanced_sexp(content: str, start: int) -> str:
    """Extract a balanced S-expression starting at the given position."""
    depth = 0
    end = start

    for i, char in enumerate(content[start:], start):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    return content[start:end]


def _find_available_symbols(content: str, limit: int = 10) -> list[str]:
    """Find symbol names in a library file."""
    # Match top-level symbols (at start of line or after opening paren at start of file)
    # KiCad v6+ files usually have (kicad_symbol_lib (symbol "Name" ...))
    pattern = r'\(symbol\s+"([^"]+)"(?:\s|\n)'
    matches = re.findall(pattern, content)
    
    # Deduplicate while preserving order, and ignore sub-units (names containing underscores and ending in numbers)
    seen = set()
    result = []
    for m in matches:
        # KiCad sub-units look like "SymbolName_0_1"
        if "_" in m and m.split("_")[-1].isdigit():
            continue
            
        if m not in seen:
            seen.add(m)
            result.append(m)
            if len(result) >= limit:
                break
    return result


def _extract_pins(symbol_content: str) -> list[PinInfo]:
    """Extract pin information from a symbol definition.
    
    Handles pins defined at any level of the symbol hierarchy (sub-units).
    """
    pins: list[PinInfo] = []

    # Improved pattern to match pin definitions:
    # Handles nested S-expressions and different property orders
    # Matches: (pin <type> <style> (at <x> <y> <angle>) ... (name "<name>" ...) (number "<num>" ...))
    pin_pattern = re.compile(r'\(pin\s+([^\s\)]+)\s+([^\s\)]+)', re.DOTALL)
    
    # We find each (pin ...) block first
    pos = 0
    while True:
        match = pin_pattern.search(symbol_content, pos)
        if not match:
            break
            
        start_idx = match.start()
        pin_block = _extract_balanced_sexp(symbol_content, start_idx)
        pos = start_idx + len(pin_block)
        
        # Parse details from within the pin block
        electrical_type = match.group(1)
        
        # Extract (at x y angle)
        at_match = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\)', pin_block)
        if not at_match:
            continue
            
        x_mm = float(at_match.group(1))
        y_mm = float(at_match.group(2))
        angle = float(at_match.group(3))
        
        # Extract (name "NAME") - name can be empty string ""
        name_match = re.search(r'\(name\s+"([^"]*)"', pin_block)
        name = name_match.group(1) if name_match else "~"
        
        # Extract (number "NUM")
        num_match = re.search(r'\(number\s+"([^"]*)"', pin_block)
        number = num_match.group(1) if num_match else "?"
        
        # Convert mm to grid units (1 grid = 0.127mm)
        # IMPORTANT: Negate Y because KiCad symbol definitions use mathematical
        # coordinates (Y up) but schematics use screen coordinates (Y down).
        # This allows pin position calculation as: component_center + pin_offset
        grid_x = round(x_mm / 0.127)
        grid_y = round(-y_mm / 0.127)  # Negate Y for schematic coordinate system

        # Determine direction from angle
        direction = _angle_to_direction(angle)

        pins.append(
            PinInfo(
                number=number,
                name=name,
                grid_offset=GridOffset(grid_x, grid_y),
                direction=direction,
                electrical_type=electrical_type,
            )
        )

    return pins


def _extract_bounding_box(symbol_content: str) -> tuple[GridOffset, GridOffset]:
    """Extract the bounding box of a symbol in grid units.
    
    Scans rectangles and polylines to find the outer dimensions.
    Returns (min_corner, max_corner).
    """
    min_x, min_y = float('inf'), float('inf')
    max_x, max_y = float('-inf'), float('-inf')
    found = False

    # Find rectangles: (rectangle (start x y) (end x y) ...)
    # Note: Y is negated to convert from symbol coords (Y up) to schematic coords (Y down)
    rect_pattern = re.compile(r'\(rectangle\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+\(end\s+([-\d.]+)\s+([-\d.]+)\)', re.DOTALL)
    for match in rect_pattern.finditer(symbol_content):
        x1, y1, x2, y2 = map(float, match.groups())
        # Negate Y values for schematic coordinate system
        y1, y2 = -y1, -y2
        min_x = min(min_x, x1, x2)
        max_x = max(max_x, x1, x2)
        min_y = min(min_y, y1, y2)
        max_y = max(max_y, y1, y2)
        found = True

    # Find polylines: (polyline (pts (xy x y) (xy x y) ...) ...)
    poly_pattern = re.compile(r'\(polyline\s+\(pts\s+([^\)]+)\)', re.DOTALL)
    for match in poly_pattern.finditer(symbol_content):
        pts_content = match.group(1)
        xy_pattern = re.compile(r'\(xy\s+([-\d.]+)\s+([-\d.]+)\)')
        for xy_match in xy_pattern.finditer(pts_content):
            x, y = map(float, xy_match.groups())
            y = -y  # Negate Y for schematic coordinate system
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)
            found = True

    # If no graphics found, use pin positions
    if not found:
        pin_at_pattern = re.compile(r'\(at\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\)')
        for match in pin_at_pattern.finditer(symbol_content):
            x, y = float(match.group(1)), float(match.group(2))
            y = -y  # Negate Y for schematic coordinate system
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)
            found = True

    if not found:
        return GridOffset(0, 0), GridOffset(0, 0)

    return (
        GridOffset(round(min_x / 0.127), round(min_y / 0.127)),
        GridOffset(round(max_x / 0.127), round(max_y / 0.127))
    )


@dataclass
class SymbolInfo:
    """Complete information about a KiCad symbol."""
    symbol_id: str
    description: str
    keywords: str
    pins: list[PinInfo]
    bounding_box_min: GridOffset
    bounding_box_max: GridOffset
    
    @property
    def width(self) -> int:
        return self.bounding_box_max.x - self.bounding_box_min.x
        
    @property
    def height(self) -> int:
        return self.bounding_box_max.y - self.bounding_box_min.y


def get_symbol_info(symbol_id: str) -> SymbolInfo:
    """Get complete information about a KiCad symbol including pins and size.
    
    Args:
        symbol_id: Symbol identifier in "Library:Symbol" format.
        
    Returns:
        SymbolInfo object.
    """
    if ":" not in symbol_id:
        raise ValueError(f"Invalid symbol_id format: '{symbol_id}'.")

    library_name, symbol_name = symbol_id.split(":", 1)
    lib_paths = get_library_paths()
    lib_file = _find_library_file(lib_paths, library_name)

    content = lib_file.read_text(errors="replace")
    symbol_start = _find_symbol_start(content, symbol_name)
    if symbol_start == -1:
        raise ValueError(f"Symbol '{symbol_name}' not found in '{library_name}'.")

    symbol_content = _extract_balanced_sexp(content, symbol_start)
    
    # Check if this symbol extends another symbol
    extends_match = re.search(r'\(extends\s+"([^"]+)"\)', symbol_content)
    if extends_match:
        base_symbol_name = extends_match.group(1)
        # Recursively get info from base symbol
        base_info = get_symbol_info(f"{library_name}:{base_symbol_name}")
        pins = base_info.pins
        description = base_info.description
        keywords = base_info.keywords
        bbox_min = base_info.bounding_box_min
        bbox_max = base_info.bounding_box_max
    else:
        pins = _extract_pins(symbol_content)
        description = ""
        keywords = ""
        bbox_min, bbox_max = _extract_bounding_box(symbol_content)
    
    # Extract/Override metadata
    desc_match = re.search(r'\(property\s+"Description"\s+"([^"]*)"', symbol_content)
    if desc_match:
        description = desc_match.group(1)
    
    key_match = re.search(r'\(property\s+"Keywords"\s+"([^"]*)"', symbol_content)
    if key_match:
        keywords = key_match.group(1)
        
    # Override bounding box if current symbol has graphics
    cur_bbox_min, cur_bbox_max = _extract_bounding_box(symbol_content)
    if cur_bbox_min != GridOffset(0, 0) or cur_bbox_max != GridOffset(0, 0):
        bbox_min, bbox_max = cur_bbox_min, cur_bbox_max
    
    return SymbolInfo(
        symbol_id=symbol_id,
        description=description,
        keywords=keywords,
        pins=pins,
        bounding_box_min=bbox_min,
        bounding_box_max=bbox_max
    )


def _angle_to_direction(angle: float) -> str:
    """Convert KiCad pin angle to direction string.

    KiCad angles indicate which way the pin points INTO the symbol:
    - 0° = pin on right side, points left into symbol
    - 90° = pin on bottom, points up into symbol
    - 180° = pin on left side, points right into symbol
    - 270° = pin on top, points down into symbol
    """
    angle = angle % 360
    if angle < 45 or angle >= 315:
        return "left"  # Pin points left (pin is on right side)
    elif 45 <= angle < 135:
        return "up"  # Pin points up (pin is on bottom)
    elif 135 <= angle < 225:
        return "right"  # Pin points right (pin is on left side)
    else:
        return "down"  # Pin points down (pin is on top)


def get_symbol_definition(symbol_id: str, library_name: Optional[str] = None, rename_to: Optional[str] = None) -> str:
    """Get the full KiCad symbol definition for embedding in schematics.

    Args:
        symbol_id: Symbol name (e.g. "R") or ID (e.g. "Device:R").
        library_name: Optional library name if symbol_id has no colon.
        rename_to: Optional new name for the symbol in the definition.

    Returns:
        The complete symbol definition as a KiCad s-expression string.
    """
    if ":" in symbol_id:
        lib_name, sym_name = symbol_id.split(":", 1)
    elif library_name:
        lib_name = library_name
        sym_name = symbol_id
    else:
        raise ValueError(f"Symbol ID '{symbol_id}' must contain a colon or library_name must be provided.")

    # Get library paths
    lib_paths = get_library_paths()
    lib_file = _find_library_file(lib_paths, lib_name)

    # Read library content
    content = lib_file.read_text(errors="replace")

    # Find the symbol definition
    symbol_start = _find_symbol_start(content, sym_name)
    if symbol_start == -1:
        raise ValueError(f"Symbol '{sym_name}' not found in library '{lib_name}'.")

    # Extract the full symbol definition
    symbol_def = _extract_balanced_sexp(content, symbol_start)

    # Rename the symbol if requested
    if rename_to:
        symbol_def = re.sub(
            rf'\(symbol\s+"{re.escape(sym_name)}"',
            f'(symbol "{rename_to}"',
            symbol_def,
            count=1
        )

    return symbol_def


def get_expanded_symbol_definition(symbol_id: str, library_name: Optional[str] = None, rename_to: Optional[str] = None) -> str:
    """Get a fully expanded KiCad symbol definition (no extends).

    KiCad 10 requires embedded symbols to be fully expanded - the 'extends' keyword
    is not supported in schematic lib_symbols. This function fetches the symbol and
    if it uses extends, merges the base symbol's graphics and pins into it.

    Args:
        symbol_id: Symbol name (e.g. "R") or ID (e.g. "Device:R").
        library_name: Optional library name if symbol_id has no colon.
        rename_to: New name for the symbol (required for KiCad 10 format).

    Returns:
        The complete expanded symbol definition as a KiCad s-expression string.
    """
    if ":" in symbol_id:
        lib_name, sym_name = symbol_id.split(":", 1)
    elif library_name:
        lib_name = library_name
        sym_name = symbol_id
    else:
        raise ValueError(f"Symbol ID '{symbol_id}' must contain a colon or library_name must be provided.")

    lib_paths = get_library_paths()
    lib_file = _find_library_file(lib_paths, lib_name)
    content = lib_file.read_text(errors="replace")

    symbol_start = _find_symbol_start(content, sym_name)
    if symbol_start == -1:
        raise ValueError(f"Symbol '{sym_name}' not found in library '{lib_name}'.")

    symbol_def = _extract_balanced_sexp(content, symbol_start)

    # Check if this symbol extends another
    extends_match = re.search(r'\(extends\s+"([^"]+)"\)', symbol_def)
    if extends_match:
        base_name = extends_match.group(1)

        # Get the base symbol definition
        base_start = _find_symbol_start(content, base_name)
        if base_start == -1:
            raise ValueError(f"Base symbol '{base_name}' not found in library '{lib_name}'.")
        base_def = _extract_balanced_sexp(content, base_start)

        # Extract sub-units (graphics and pins) from base symbol
        # These are sections like (symbol "BaseName_0_1" ...) and (symbol "BaseName_1_1" ...)
        base_subunits = []
        subunit_pattern = re.compile(rf'\(symbol\s+"{re.escape(base_name)}_(\d+_\d+)"')
        for match in subunit_pattern.finditer(base_def):
            subunit_start = match.start()
            subunit_def = _extract_balanced_sexp(base_def, subunit_start)
            base_subunits.append((match.group(1), subunit_def))

        # Remove the extends line from the derived symbol
        symbol_def = re.sub(r'\s*\(extends\s+"[^"]+"\)\s*', '\n', symbol_def)

        # Find where to insert the sub-units (before (embedded_fonts ...))
        embedded_fonts_match = re.search(r'\(embedded_fonts', symbol_def)
        if embedded_fonts_match:
            insert_pos = embedded_fonts_match.start()
        else:
            # Insert before the final closing paren
            insert_pos = symbol_def.rfind(')')

        # Build sub-units with the new name
        new_name = rename_to if rename_to else sym_name
        subunits_str = ""
        for suffix, subunit_def in base_subunits:
            # Rename the sub-unit from "BaseName_X_Y" to "NewName_X_Y"
            renamed_subunit = re.sub(
                rf'\(symbol\s+"{re.escape(base_name)}_{suffix}"',
                f'(symbol "{new_name}_{suffix}"',
                subunit_def
            )
            subunits_str += "\n\t\t" + renamed_subunit.replace("\n", "\n\t\t")

        # Insert sub-units
        symbol_def = symbol_def[:insert_pos] + subunits_str + "\n\t\t" + symbol_def[insert_pos:]

    # Rename the main symbol
    if rename_to:
        symbol_def = re.sub(
            rf'\(symbol\s+"{re.escape(sym_name)}"',
            f'(symbol "{rename_to}"',
            symbol_def,
            count=1
        )
        # Also rename any sub-units that use the original name
        symbol_def = re.sub(
            rf'\(symbol\s+"{re.escape(sym_name)}_(\d+_\d+)"',
            rf'(symbol "{rename_to}_\1"',
            symbol_def
        )

    return symbol_def

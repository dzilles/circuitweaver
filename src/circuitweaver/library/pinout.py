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
    """X, Y offset in grid units."""

    x: int
    y: int


@dataclass
class PinInfo:
    """Detailed information about a symbol pin."""

    number: str
    name: str
    grid_offset: GridOffset
    direction: str  # "left", "right", "up", "down"
    electrical_type: str


@dataclass
class SymbolInfo:
    """Detailed information about a KiCad symbol."""

    symbol_id: str
    name: str
    pins: list[PinInfo]
    bounding_box_min: GridOffset
    bounding_box_max: GridOffset

    @property
    def width(self) -> int:
        """Width in grid units."""
        return self.bounding_box_max.x - self.bounding_box_min.x

    @property
    def height(self) -> int:
        """Height in grid units."""
        return self.bounding_box_max.y - self.bounding_box_min.y


def get_symbol_pinout(symbol_id: str) -> list[PinInfo]:
    """Get pin information for a KiCad symbol."""
    info = get_symbol_info(symbol_id)
    return info.pins


def get_symbol_info(symbol_id: str) -> SymbolInfo:
    """Extract full symbol information including bounding box."""
    lib_paths = get_library_paths()
    parts = symbol_id.split(":", 1)
    if len(parts) < 2:
        raise ValueError(f"Invalid symbol ID: {symbol_id}. Expected 'library:symbol'")

    lib_name, sym_name = parts
    lib_file = lib_paths.symbols / f"{lib_name}.kicad_sym"

    if not lib_file.exists():
        raise ValueError(f"Library file not found: {lib_file}")

    content = lib_file.read_text(errors="replace")
    symbol_start = _find_symbol_start(content, sym_name)
    if symbol_start == -1:
        raise ValueError(f"Symbol '{sym_name}' not found in library '{lib_name}'")

    symbol_content = _extract_balanced_sexp(content, symbol_start)
    
    # Check for extension: (extends "BASE_NAME")
    extends_match = re.search(r'\(extends\s+"([^"]+)"', symbol_content)
    if extends_match:
        base_name = extends_match.group(1)
        # Recursively get info for the base symbol
        return get_symbol_info(f"{lib_name}:{base_name}")

    pins = _extract_pins(symbol_content)

    if not pins:
        return SymbolInfo(
            symbol_id=symbol_id, name=sym_name, pins=[],
            bounding_box_min=GridOffset(0, 0), bounding_box_max=GridOffset(40, 40),
        )

    min_x = min(p.grid_offset.x for p in pins)
    max_x = max(p.grid_offset.x for p in pins)
    min_y = min(p.grid_offset.y for p in pins)
    max_y = max(p.grid_offset.y for p in pins)

    # Return tight bounding box (no padding)
    return SymbolInfo(
        symbol_id=symbol_id,
        name=sym_name,
        pins=pins,
        bounding_box_min=GridOffset(min_x, min_y),
        bounding_box_max=GridOffset(max_x, max_y),
    )


def _find_symbol_start(content: str, symbol_name: str) -> int:
    # Match (symbol "NAME" ...)
    pattern = rf'\(symbol\s+"{re.escape(symbol_name)}"'
    match = re.search(pattern, content)
    return match.start() if match else -1


def _extract_balanced_sexp(content: str, start_pos: int) -> str:
    bracket_level = 0
    in_string = False
    escape = False
    for i in range(start_pos, len(content)):
        char = content[i]
        if escape:
            escape = False; continue
        if char == '"': in_string = not in_string
        elif char == "\\" and in_string: escape = True
        elif not in_string:
            if char == "(": bracket_level += 1
            elif char == ")":
                bracket_level -= 1
                if bracket_level == 0: return content[start_pos : i + 1]
    return content[start_pos:]


def _extract_pins(symbol_content: str) -> list[PinInfo]:
    pins: list[PinInfo] = []
    # Match (pin ELECTRICAL_TYPE GRAPHIC_TYPE (at X Y ANGLE) ... (name "NAME" ...) (number "NUMBER" ...))
    # Note: ELECTRICAL_TYPE can be quoted or unquoted.
    pin_pattern = re.compile(r'\(pin\s+([^\s\)]+)\s+([^\s\)]+)', re.DOTALL)
    
    # Iterate through the content to find ALL pins, including those in nested (symbol ...) blocks
    pos = 0
    while True:
        match = pin_pattern.search(symbol_content, pos)
        if not match:
            break
        
        start_idx = match.start()
        # Extract the full pin block to find name/number within it
        pin_block = _extract_balanced_sexp(symbol_content, start_idx)
        pos = start_idx + len(pin_block)
        
        electrical_type = match.group(1).strip('"')
        
        at_match = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\)', pin_block)
        if not at_match:
            continue
            
        x_mm = float(at_match.group(1))
        y_mm = float(at_match.group(2))
        angle = float(at_match.group(3))
        
        name_match = re.search(r'\(name\s+"([^"]*)"', pin_block)
        name = name_match.group(1) if name_match else ""
        
        num_match = re.search(r'\(number\s+"([^"]*)"', pin_block)
        number = num_match.group(1) if num_match else ""
        
        # Convert KiCad mm to our grid units (1 grid = 0.127mm)
        grid_x = int(round(x_mm / 0.127))
        grid_y = int(round(y_mm / 0.127))
        
        pins.append(PinInfo(
            number=number,
            name=name,
            grid_offset=GridOffset(grid_x, grid_y),
            direction=_angle_to_direction(angle),
            electrical_type=electrical_type
        ))
        
    return pins


def _angle_to_direction(angle: float) -> str:
    angle = angle % 360
    if angle == 0: return "right"
    if angle == 90: return "up"
    if angle == 180: return "left"
    if angle == 270: return "down"
    return "right"


def get_expanded_symbol_definition(symbol_name: str, library_name: str, rename_to: Optional[str] = None) -> str:
    """Get the full symbol definition for embedding with recursive renaming."""
    lib_paths = get_library_paths()
    lib_file = lib_paths.symbols / f"{library_name}.kicad_sym"
    if not lib_file.exists(): raise ValueError(f"Library not found: {library_name}")
    content = lib_file.read_text(errors="replace")
    symbol_start = _find_symbol_start(content, symbol_name)
    if symbol_start == -1: raise ValueError(f"Symbol {symbol_name} not found")
    symbol_def = _extract_balanced_sexp(content, symbol_start)
    if rename_to:
        symbol_def = re.sub(rf'^\(symbol\s+"{re.escape(symbol_name)}"', f'(symbol "{rename_to}"', symbol_def)
        symbol_def = symbol_def.replace(f'"{symbol_name}_', f'"{rename_to}_')
    return symbol_def

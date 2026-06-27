import logging
import re
from functools import lru_cache
from typing import Any, NamedTuple

import sexpdata

from circuitweaver.types import GridOffset

from .paths import get_library_paths

logger = logging.getLogger(__name__)


class Pin(NamedTuple):
    """Pin information from a KiCad symbol."""

    number: str
    name: str
    grid_offset: GridOffset
    direction: str
    electrical_type: str = "passive"


class SymbolInfo(NamedTuple):
    symbol_id: str
    name: str
    pins: list[Pin]
    bounding_box_min: GridOffset
    bounding_box_max: GridOffset

    @property
    def width(self) -> int:
        return self.bounding_box_max.x - self.bounding_box_min.x

    @property
    def height(self) -> int:
        return self.bounding_box_max.y - self.bounding_box_min.y


class SymbolAdapter:
    """
    Adapter for translating between KiCad S-expression data and SymbolInfo.
    """

    @staticmethod
    def _is_symbol(item: Any, key: str) -> bool:
        """Checks if an item is a sexpdata.Symbol matching the key."""
        if isinstance(item, sexpdata.Symbol):
            return item.value() == key
        return str(item) == key

    def _get_list(self, sexp: list[Any], key: str) -> list[Any] | None:
        """Finds a sub-list starting with the given key symbol."""
        for item in sexp:
            if isinstance(item, list) and len(item) > 0 and self._is_symbol(item[0], key):
                return item
        return None

    def _get_all_lists(self, sexp: list[Any], key: str) -> list[list[Any]]:
        """Finds all sub-lists starting with the given key symbol."""
        return [item for item in sexp if isinstance(item, list) and len(item) > 0 and self._is_symbol(item[0], key)]

    def _get_str(self, item: Any) -> str:
        """Safely converts a sexpdata item (Symbol or string) to a string."""
        if isinstance(item, sexpdata.Symbol):
            return item.value()
        return str(item)

    def _find_all_recursive(self, sexp: list[Any], key: str) -> list[list[Any]]:
        """Recursively finds all sub-lists starting with the given key symbol."""
        results = []
        if not isinstance(sexp, list) or not sexp:
            return results

        if self._is_symbol(sexp[0], key):
            results.append(sexp)

        for item in sexp:
            if isinstance(item, list):
                # Don't recurse into nested symbols if we are looking for 'symbol' blocks themselves
                # but we DO want to recurse to find 'pin' or 'rectangle' inside 'symbol' blocks.
                results.extend(self._find_all_recursive(item, key))
        return results

    def extract_pins(self, symbol_sexp: list[Any]) -> list[Pin]:
        """Extracts pin information from a parsed symbol S-expression, including nested symbol blocks."""
        pins = []
        # KiCad pins are in (pin electrical_type graphical_style (at X Y ANGLE) ...)
        # They can be at the top level of a symbol or inside nested symbol blocks (e.g. NAME_1_1)
        for pin_sexp in self._find_all_recursive(symbol_sexp, "pin"):
            elec_type = self._get_str(pin_sexp[1]) if len(pin_sexp) > 1 else "passive"

            at_list = self._get_list(pin_sexp, "at")
            if not at_list or len(at_list) < 4:
                continue

            x_mm, y_mm = float(at_list[1]), float(at_list[2])
            angle = int(at_list[3])

            num_list = self._get_list(pin_sexp, "number")
            number = self._get_str(num_list[1]) if num_list and len(num_list) > 1 else "?"

            name_list = self._get_list(pin_sexp, "name")
            name = self._get_str(name_list[1]) if name_list and len(name_list) > 1 else "?"

            # Convert mm to grid units (1 grid = 0.127mm)
            # Note: In symbols, Y goes UP. In schematics, Y goes DOWN. Negate Y.
            grid_offset = GridOffset(x=int(round(x_mm / 0.127)), y=int(round(-y_mm / 0.127)))

            pins.append(Pin(
                number=number,
                name=name,
                grid_offset=grid_offset,
                direction=self._angle_to_direction(angle),
                electrical_type=elec_type
            ))
        return pins

    def extract_graphic_bounds(self, symbol_sexp: list[Any]) -> tuple[float, float, float, float] | None:
        """Calculates bounding box of graphical elements in mm, including nested symbol blocks."""
        xs, ys = [], []

        # 1. Rectangles: (rectangle (start X Y) (end X Y))
        for rect in self._find_all_recursive(symbol_sexp, "rectangle"):
            start = self._get_list(rect, "start")
            end = self._get_list(rect, "end")
            if start and end:
                xs.extend([float(start[1]), float(end[1])])
                ys.extend([float(start[2]), float(end[2])])

        # 2. Arcs: (arc (start X Y) (mid X Y) (end X Y))
        for arc in self._find_all_recursive(symbol_sexp, "arc"):
            start = self._get_list(arc, "start")
            mid = self._get_list(arc, "mid")
            end = self._get_list(arc, "end")
            if start and mid and end:
                xs.extend([float(start[1]), float(mid[1]), float(end[1])])
                ys.extend([float(start[2]), float(mid[2]), float(end[2])])

        # 3. Circles: (circle (center X Y) (radius R))
        for circ in self._find_all_recursive(symbol_sexp, "circle"):
            center = self._get_list(circ, "center")
            radius_list = self._get_list(circ, "radius")
            if center and radius_list:
                cx, cy = float(center[1]), float(center[2])
                r = float(radius_list[1])
                xs.extend([cx - r, cx + r])
                ys.extend([cy - r, cy + r])

        # 4. Polylines: (polyline (pts (xy X Y) (xy X Y) ...))
        for poly in self._find_all_recursive(symbol_sexp, "polyline"):
            pts_list = self._get_list(poly, "pts")
            if pts_list:
                for xy in self._get_all_lists(pts_list, "xy"):
                    xs.append(float(xy[1]))
                    ys.append(float(xy[2]))

        if not xs or not ys:
            return None

        return min(xs), max(xs), min(ys), max(ys)

    def _angle_to_direction(self, angle: int) -> str:
        if angle == 0:
            return "right"
        if angle == 90:
            return "up"
        if angle == 180:
            return "left"
        if angle == 270:
            return "down"
        return "right"


@lru_cache(maxsize=128)
def get_symbol_info(symbol_id: str) -> SymbolInfo:
    """
    Retrieves information about a KiCad symbol, resolving inheritance.
    """
    lib_name, sym_name = symbol_id.split(":", 1)
    lib_paths = get_library_paths()
    lib_file = lib_paths.symbols / f"{lib_name}.kicad_sym"

    if not lib_file.exists():
        raise ValueError(f"Library file not found for {lib_name}")

    content = lib_file.read_text(errors="replace")
    try:
        lib_sexp = sexpdata.loads(content)

        adapter = SymbolAdapter()
        if isinstance(lib_sexp, list) and len(lib_sexp) > 0 and adapter._is_symbol(lib_sexp[0], "kicad_symbol_lib"):
            lib_sexp = lib_sexp[1:]
    except Exception as e:
        logger.error(f"Failed to parse S-Expression in {lib_file}: {e}")
        raise ValueError(f"Malformed S-Expression in library '{lib_name}'") from e

    # Find the symbol in the library
    symbol_sexp = None
    for item in lib_sexp:
        if isinstance(item, list) and len(item) > 1 and adapter._is_symbol(item[0], "symbol"):
            item_id = adapter._get_str(item[1])
            if item_id == sym_name:
                symbol_sexp = item
                break

    if not symbol_sexp:
        raise ValueError(f"Symbol '{sym_name}' not found in library '{lib_name}'")

    # Handle Inheritance (extends "...")
    extends_list = adapter._get_list(symbol_sexp, "extends")
    pins = []
    graphic_bounds = None

    if extends_list and len(extends_list) > 1:
        base_name = adapter._get_str(extends_list[1])
        base_sexp = None
        for item in lib_sexp:
            if isinstance(item, list) and len(item) > 1 and adapter._is_symbol(item[0], "symbol"):
                item_id = adapter._get_str(item[1])
                if item_id == base_name:
                    base_sexp = item
                    break

        if not base_sexp:
            raise ValueError(f"Base symbol '{base_name}' not found for '{sym_name}'")

        # Merge pins and graphics from base
        pins = adapter.extract_pins(base_sexp)
        graphic_bounds = adapter.extract_graphic_bounds(base_sexp)

        # Overlay pins/graphics from the inheriting symbol if present
        local_pins = adapter.extract_pins(symbol_sexp)
        if local_pins:
            # We merge pins for KiCad inheritance if local pins exist
            # (Though usually KiCad replaces the whole pin set if it defines any)
            # For now, let's keep the local ones if they exist, otherwise base.
            pins = local_pins

        local_bounds = adapter.extract_graphic_bounds(symbol_sexp)
        if local_bounds:
            if graphic_bounds:
                graphic_bounds = (
                    min(graphic_bounds[0], local_bounds[0]),
                    max(graphic_bounds[1], local_bounds[1]),
                    min(graphic_bounds[2], local_bounds[2]),
                    max(graphic_bounds[3], local_bounds[3])
                )
            else:
                graphic_bounds = local_bounds
    else:
        pins = adapter.extract_pins(symbol_sexp)
        graphic_bounds = adapter.extract_graphic_bounds(symbol_sexp)

    # Calculate final bounding box in grid units
    xs, ys = [], []
    if graphic_bounds:
        min_x_mm, max_x_mm, min_y_mm, max_y_mm = graphic_bounds
        xs.extend([int(round(min_x_mm / 0.127)), int(round(max_x_mm / 0.127))])
        # Note: Negate Y for schematic coordinates
        ys.extend([int(round(-max_y_mm / 0.127)), int(round(-min_y_mm / 0.127))])

    for p in pins:
        xs.append(p.grid_offset.x)
        ys.append(p.grid_offset.y)

    if not xs or not ys:
        raise ValueError(f"Symbol '{symbol_id}' has no geometry or pins.")

    return SymbolInfo(
        symbol_id=symbol_id,
        name=sym_name,
        pins=pins,
        bounding_box_min=GridOffset(x=min(xs), y=min(ys)),
        bounding_box_max=GridOffset(x=max(xs), y=max(ys)),
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
            escape = False
            continue
        if char == '"':
            in_string = not in_string
        elif char == "\\" and in_string:
            escape = True
        elif not in_string:
            if char == "(":
                bracket_level += 1
            elif char == ")":
                bracket_level -= 1
                if bracket_level == 0:
                    return content[start_pos : i + 1]
    return content[start_pos:]


@lru_cache(maxsize=128)
def get_expanded_symbol_definition(symbol_id: str, library_name: str, rename_to: str | None = None) -> str:
    """Get the full symbol definition for embedding, recursively handling extensions."""
    lib_paths = get_library_paths()
    lib_file = lib_paths.symbols / f"{library_name}.kicad_sym"
    if not lib_file.exists():
        raise ValueError(f"Library not found: {library_name}")

    content = lib_file.read_text(errors="replace")
    # symbol_id might be "Lib:Name", we want "Name" for searching in the library file
    symbol_name = symbol_id.split(":")[-1] if ":" in symbol_id else symbol_id

    symbol_start = _find_symbol_start(content, symbol_name)
    if symbol_start == -1:
        raise ValueError(f"Symbol {symbol_name} not found in {library_name}")

    symbol_def = _extract_balanced_sexp(content, symbol_start)

    # Check for extension: (extends "BASE_NAME")
    extends_match = re.search(r'\(extends\s+"([^"]+)"\)', symbol_def)
    if extends_match:
        base_name = extends_match.group(1)
        # Fetch the FULLY EXPANDED base definition (recursively)
        base_def = get_expanded_symbol_definition(base_name, library_name)

        # Remove (extends ...) from child
        symbol_def = symbol_def.replace(extends_match.group(0), "")

        # Extract the content from the base symbol (everything between first (symbol "NAME" ...) and last )
        base_start = base_def.find('(')
        if base_start != -1:
            base_inner = _extract_balanced_sexp(base_def, base_start)
            # Find everything inside the base_inner: (symbol "NAME" <HERE>)
            inner_match = re.search(rf'\(symbol\s+"{re.escape(base_name)}"\s+(.*)\)\s*$', base_inner, re.DOTALL)
            if inner_match:
                base_content = inner_match.group(1)

                # Rename the base_name prefixes to symbol_name in base_content
                base_content = base_content.replace(f'"{base_name}_', f'"{symbol_name}_')
                base_content = base_content.replace(f'"{base_name}"', f'"{symbol_name}"')

                # Merge into child: Find the index of the LAST closing paren
                last_paren_idx = symbol_def.rfind(')')
                if last_paren_idx != -1:
                    symbol_def = symbol_def[:last_paren_idx] + "\n    " + base_content + "\n  )"

    if rename_to:
        # Rename the main symbol and ALL internal references (units, etc)
        # We use a greedy replace for the name but ensure we don't hit parts of other tokens
        symbol_def = symbol_def.replace(f'"{symbol_name}"', f'"{rename_to}"')
        symbol_def = symbol_def.replace(f'"{symbol_name}_', f'"{rename_to}_')
        # Also catch the case where the name might be used in a property without quotes (rare but possible)
        symbol_def = re.sub(rf'\(symbol\s+"?{re.escape(symbol_name)}"?', f'(symbol "{rename_to}"', symbol_def)

    return symbol_def

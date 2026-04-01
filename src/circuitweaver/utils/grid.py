"""Grid coordinate utilities."""

# Standard KiCad grid: 1 grid unit = 2.54mm (0.1 inch)
GRID_SIZE_MM = 2.54


def grid_to_mm(grid_value: int) -> float:
    """Convert grid units to millimeters.

    Args:
        grid_value: Value in grid units (integers).

    Returns:
        Value in millimeters.
    """
    return grid_value * GRID_SIZE_MM


def mm_to_grid(mm_value: float) -> int:
    """Convert millimeters to grid units.

    Args:
        mm_value: Value in millimeters.

    Returns:
        Nearest grid unit (integer).
    """
    return round(mm_value / GRID_SIZE_MM)


def snap_to_grid(mm_value: float) -> float:
    """Snap a millimeter value to the nearest grid point.

    Args:
        mm_value: Value in millimeters.

    Returns:
        Snapped value in millimeters.
    """
    grid = mm_to_grid(mm_value)
    return grid_to_mm(grid)


def grid_distance(x1: int, y1: int, x2: int, y2: int) -> float:
    """Calculate Manhattan distance between two grid points.

    Args:
        x1, y1: First point in grid units.
        x2, y2: Second point in grid units.

    Returns:
        Manhattan distance in grid units.
    """
    return abs(x2 - x1) + abs(y2 - y1)


def euclidean_distance(x1: int, y1: int, x2: int, y2: int) -> float:
    """Calculate Euclidean distance between two grid points.

    Args:
        x1, y1: First point in grid units.
        x2, y2: Second point in grid units.

    Returns:
        Euclidean distance in grid units.
    """
    return ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

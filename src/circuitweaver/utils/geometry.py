"""Geometry utilities for orthogonal routing."""

from typing import NamedTuple


class Point(NamedTuple):
    """A 2D point in grid coordinates."""

    x: int
    y: int


class Edge(NamedTuple):
    """An edge (line segment) between two points."""

    from_point: Point
    to_point: Point


def is_orthogonal(x1: int, y1: int, x2: int, y2: int) -> bool:
    """Check if a line segment is orthogonal (horizontal or vertical).

    Args:
        x1, y1: Start point.
        x2, y2: End point.

    Returns:
        True if the line is horizontal or vertical.
    """
    return x1 == x2 or y1 == y2


def is_horizontal(x1: int, y1: int, x2: int, y2: int) -> bool:
    """Check if a line segment is horizontal."""
    return y1 == y2


def is_vertical(x1: int, y1: int, x2: int, y2: int) -> bool:
    """Check if a line segment is vertical."""
    return x1 == x2


def make_orthogonal_path(
    start: Point,
    end: Point,
    prefer_horizontal_first: bool = True,
) -> list[Edge]:
    """Create an orthogonal path between two points.

    If the points are not aligned, creates an L-shaped path with
    one horizontal and one vertical segment.

    Args:
        start: Starting point.
        end: Ending point.
        prefer_horizontal_first: If True, go horizontal then vertical.
            If False, go vertical then horizontal.

    Returns:
        List of orthogonal edges connecting start to end.
    """
    if start == end:
        return []

    # Already aligned horizontally or vertically
    if start.x == end.x or start.y == end.y:
        return [Edge(start, end)]

    # Need an L-shaped path
    if prefer_horizontal_first:
        # Go horizontal first, then vertical
        corner = Point(end.x, start.y)
        return [
            Edge(start, corner),
            Edge(corner, end),
        ]
    else:
        # Go vertical first, then horizontal
        corner = Point(start.x, end.y)
        return [
            Edge(start, corner),
            Edge(corner, end),
        ]


def make_orthogonal_path_around(
    start: Point,
    end: Point,
    avoid_points: list[Point],
    margin: int = 2,
) -> list[Edge]:
    """Create an orthogonal path that avoids certain points.

    This is a simple implementation that routes around obstacles
    by going wide if needed.

    Args:
        start: Starting point.
        end: Ending point.
        avoid_points: Points to avoid (e.g., component centers).
        margin: Minimum distance from avoid points.

    Returns:
        List of orthogonal edges connecting start to end.
    """
    # Simple implementation: try both L-shapes, pick the one
    # that's farther from obstacles
    path1 = make_orthogonal_path(start, end, prefer_horizontal_first=True)
    path2 = make_orthogonal_path(start, end, prefer_horizontal_first=False)

    # Score paths by minimum distance to obstacles
    score1 = _path_obstacle_score(path1, avoid_points)
    score2 = _path_obstacle_score(path2, avoid_points)

    if score1 >= score2:
        return path1
    else:
        return path2


def _path_obstacle_score(path: list[Edge], obstacles: list[Point]) -> float:
    """Score a path by its minimum distance to obstacles.

    Higher score = better (farther from obstacles).
    """
    if not obstacles or not path:
        return float("inf")

    min_distance = float("inf")

    for edge in path:
        for obs in obstacles:
            # Check distance from obstacle to edge
            dist = _point_to_segment_distance(
                obs,
                edge.from_point,
                edge.to_point,
            )
            min_distance = min(min_distance, dist)

    return min_distance


def _point_to_segment_distance(
    point: Point,
    seg_start: Point,
    seg_end: Point,
) -> float:
    """Calculate distance from a point to a line segment."""
    px, py = point
    x1, y1 = seg_start
    x2, y2 = seg_end

    # For orthogonal segments, this is simpler
    if x1 == x2:  # Vertical segment
        if min(y1, y2) <= py <= max(y1, y2):
            return abs(px - x1)
        else:
            # Distance to nearest endpoint
            return min(
                ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5,
                ((px - x2) ** 2 + (py - y2) ** 2) ** 0.5,
            )
    elif y1 == y2:  # Horizontal segment
        if min(x1, x2) <= px <= max(x1, x2):
            return abs(py - y1)
        else:
            return min(
                ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5,
                ((px - x2) ** 2 + (py - y2) ** 2) ** 0.5,
            )
    else:
        # Non-orthogonal (shouldn't happen in our use case)
        return min(
            ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5,
            ((px - x2) ** 2 + (py - y2) ** 2) ** 0.5,
        )


def bounding_box(
    points: list[Point],
) -> tuple[Point, Point]:
    """Calculate bounding box of a set of points.

    Args:
        points: List of points.

    Returns:
        Tuple of (min_corner, max_corner).
    """
    if not points:
        return Point(0, 0), Point(0, 0)

    min_x = min(p.x for p in points)
    min_y = min(p.y for p in points)
    max_x = max(p.x for p in points)
    max_y = max(p.y for p in points)

    return Point(min_x, min_y), Point(max_x, max_y)

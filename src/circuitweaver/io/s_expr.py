"""S-expression file I/O for KiCad files.

Handles reading and writing of S-expression files like .kicad_sch.
"""

from pathlib import Path

from circuitweaver.types.s_expr import SExpr, parse, serialize


def read_s_expr(file_path: Path) -> SExpr:
    """Read an S-expression file into an SExpr tree.

    Args:
        file_path: Path to the S-expression file (e.g., .kicad_sch).

    Returns:
        Parsed SExpr tree.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ParseError: If the file contains malformed S-expressions.
    """
    content = file_path.read_text(encoding="utf-8", errors="replace")
    return parse(content)


def write_s_expr(file_path: Path, sexp: SExpr) -> None:
    """Write an SExpr tree to a file.

    Args:
        file_path: Path to write the S-expression file.
        sexp: SExpr tree to serialize.
    """
    content = serialize(sexp)
    file_path.write_text(content, encoding="utf-8")

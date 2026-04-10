"""S-expression types for KiCad file format.

S-expressions are the native format for KiCad schematic files (.kicad_sch).
This module provides types for building and parsing S-expression trees.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, List, Union


class RawString:
    """A string that should not be quoted or escaped when serialized.

    Use this for embedding pre-formatted S-expression content.
    """

    def __init__(self, value: str):
        self.value = value

    def __repr__(self) -> str:
        return f"RawString({self.value!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, RawString):
            return self.value == other.value
        return False


@dataclass
class SExpr:
    """An S-expression node.

    Represents a parenthesized expression like (name arg1 arg2 ...).

    Examples:
        SExpr("wire", SExpr("pts", ...), SExpr("stroke", ...))
        SExpr("at", 10.5, 20.3, 0)
    """

    name: str
    args: List[Any] = field(default_factory=list)

    def __init__(self, name: str, *args: Any):
        self.name = name
        self.args = list(args)

    def __repr__(self) -> str:
        if not self.args:
            return f"SExpr({self.name!r})"
        args_repr = ", ".join(repr(a) for a in self.args[:3])
        if len(self.args) > 3:
            args_repr += ", ..."
        return f"SExpr({self.name!r}, {args_repr})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SExpr):
            return self.name == other.name and self.args == other.args
        return False

    def find(self, name: str) -> "SExpr | None":
        """Find first child SExpr with the given name."""
        for arg in self.args:
            if isinstance(arg, SExpr) and arg.name == name:
                return arg
        return None

    def find_all(self, name: str) -> List["SExpr"]:
        """Find all child SExprs with the given name."""
        return [arg for arg in self.args if isinstance(arg, SExpr) and arg.name == name]

    def get_value(self, name: str, default: Any = None) -> Any:
        """Get the first argument of a child SExpr by name.

        Example:
            sexp = SExpr("symbol", SExpr("at", 10, 20), SExpr("unit", 1))
            sexp.get_value("unit")  # Returns 1
        """
        child = self.find(name)
        if child and child.args:
            return child.args[0]
        return default


# Type alias for S-expression values
SExprValue = Union[SExpr, RawString, str, int, float, Decimal, bool, None]


def format_value(val: Any) -> str:
    """Format a single value for S-expression output."""
    if val is None:
        return ""
    if isinstance(val, SExpr):
        return serialize(val)
    if isinstance(val, RawString):
        return val.value
    if isinstance(val, bool):
        return "yes" if val else "no"
    if isinstance(val, (int, float, Decimal)):
        return str(val)

    s = str(val)
    # Quote if contains special characters, is empty, or is all digits
    if any(c in s for c in ' ()"\t\n:;/') or not s or s.isdigit():
        escaped = s.replace('"', '\\"')
        return f'"{escaped}"'
    return s


def serialize(sexp: SExpr, indent_level: int = 0) -> str:
    """Serialize an SExpr to a string with proper indentation."""
    indent = "  " * indent_level

    if not sexp.args:
        return f"{indent}({sexp.name})"

    # Check if we should use multiline format
    is_multiline = (
        len(sexp.args) > 5 or
        any(isinstance(arg, RawString) and "\n" in arg.value for arg in sexp.args) or
        any(isinstance(arg, SExpr) for arg in sexp.args) or
        any(isinstance(arg, (list, tuple)) and any(isinstance(i, SExpr) for i in arg) for arg in sexp.args)
    )

    if not is_multiline:
        args_formatted = [format_value(arg) for arg in sexp.args]
        args_str = " ".join(f for f in args_formatted if f)
        return f"{indent}({sexp.name} {args_str})"
    else:
        lines = [f"{indent}({sexp.name}"]
        for arg in sexp.args:
            if isinstance(arg, SExpr):
                lines.append(serialize(arg, indent_level + 1))
            elif isinstance(arg, RawString):
                for rl in arg.value.split("\n"):
                    if rl.strip():
                        lines.append("  " * (indent_level + 1) + rl.strip())
            elif isinstance(arg, (list, tuple)):
                for item in arg:
                    if isinstance(item, SExpr):
                        lines.append(serialize(item, indent_level + 1))
                    else:
                        f = format_value(item)
                        if f:
                            lines.append("  " * (indent_level + 1) + f)
            else:
                f = format_value(arg)
                if f:
                    lines.append("  " * (indent_level + 1) + f)
        lines.append(f"{indent})")
        return "\n".join(lines)


class ParseError(Exception):
    """Error parsing S-expression."""
    pass


def parse(text: str) -> SExpr:
    """Parse an S-expression string into an SExpr tree.

    Args:
        text: S-expression string like "(name arg1 arg2 (nested ...))"

    Returns:
        Parsed SExpr tree.

    Raises:
        ParseError: If the input is malformed.
    """
    tokens = _tokenize(text)
    if not tokens:
        raise ParseError("Empty input")

    result, remaining = _parse_expr(tokens)
    return result


def _tokenize(text: str) -> List[str]:
    """Tokenize S-expression text into a list of tokens."""
    tokens = []
    i = 0
    n = len(text)

    while i < n:
        c = text[i]

        # Skip whitespace
        if c in ' \t\n\r':
            i += 1
            continue

        # Parentheses
        if c == '(':
            tokens.append('(')
            i += 1
            continue
        if c == ')':
            tokens.append(')')
            i += 1
            continue

        # Quoted string
        if c == '"':
            j = i + 1
            while j < n:
                if text[j] == '\\' and j + 1 < n:
                    j += 2
                elif text[j] == '"':
                    break
                else:
                    j += 1
            # Include quotes in token for later processing
            tokens.append(text[i:j + 1])
            i = j + 1
            continue

        # Atom (unquoted)
        j = i
        while j < n and text[j] not in ' \t\n\r()':
            j += 1
        tokens.append(text[i:j])
        i = j

    return tokens


def _parse_expr(tokens: List[str]) -> tuple[SExpr, List[str]]:
    """Parse tokens into an SExpr, returning (result, remaining_tokens)."""
    if not tokens:
        raise ParseError("Unexpected end of input")

    if tokens[0] != '(':
        raise ParseError(f"Expected '(', got {tokens[0]!r}")

    tokens = tokens[1:]  # consume '('

    if not tokens:
        raise ParseError("Unexpected end of input after '('")

    # First token after '(' is the name
    name = _parse_atom(tokens[0])
    tokens = tokens[1:]

    args = []
    while tokens and tokens[0] != ')':
        if tokens[0] == '(':
            child, tokens = _parse_expr(tokens)
            args.append(child)
        else:
            args.append(_parse_atom(tokens[0]))
            tokens = tokens[1:]

    if not tokens:
        raise ParseError("Unexpected end of input, expected ')'")

    tokens = tokens[1:]  # consume ')'

    return SExpr(name, *args), tokens


def _parse_atom(token: str) -> Union[str, int, float, bool]:
    """Parse a single atom token into a Python value."""
    # Quoted string
    if token.startswith('"') and token.endswith('"'):
        inner = token[1:-1]
        # Unescape
        return inner.replace('\\"', '"').replace('\\\\', '\\')

    # Boolean
    if token == "yes":
        return True
    if token == "no":
        return False

    # Number
    try:
        if '.' in token:
            return float(token)
        return int(token)
    except ValueError:
        pass

    # Plain string/symbol
    return token

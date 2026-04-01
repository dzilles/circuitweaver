"""Custom exception types for CircuitWeaver."""

from typing import Optional


class CircuitWeaverError(Exception):
    """Base exception for all CircuitWeaver errors."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            detail_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.message} ({detail_str})"
        return self.message


class ValidationError(CircuitWeaverError):
    """Raised when Circuit JSON validation fails."""

    def __init__(
        self,
        message: str,
        rule: Optional[str] = None,
        element_id: Optional[str] = None,
        location: Optional[dict] = None,
    ):
        details = {}
        if rule:
            details["rule"] = rule
        if element_id:
            details["element_id"] = element_id
        if location:
            details["location"] = location
        super().__init__(message, details)
        self.rule = rule
        self.element_id = element_id
        self.location = location


class CompilationError(CircuitWeaverError):
    """Raised when compilation to KiCad format fails."""

    def __init__(
        self,
        message: str,
        phase: Optional[str] = None,
        element_id: Optional[str] = None,
    ):
        details = {}
        if phase:
            details["phase"] = phase
        if element_id:
            details["element_id"] = element_id
        super().__init__(message, details)
        self.phase = phase
        self.element_id = element_id


class ERCError(CircuitWeaverError):
    """Raised when Electrical Rules Check fails."""

    def __init__(
        self,
        message: str,
        severity: str = "error",
        location: Optional[str] = None,
    ):
        details = {"severity": severity}
        if location:
            details["location"] = location
        super().__init__(message, details)
        self.severity = severity
        self.location = location


class KiCadNotFoundError(CircuitWeaverError):
    """Raised when KiCad CLI is not available."""

    def __init__(self, command: str = "kicad-cli"):
        super().__init__(
            f"KiCad CLI not found: '{command}'. Please install KiCad 10.0 or later.",
            {"command": command},
        )
        self.command = command


class LibraryNotFoundError(CircuitWeaverError):
    """Raised when a KiCad library cannot be found."""

    def __init__(self, library_id: str, library_type: str = "symbol"):
        super().__init__(
            f"{library_type.title()} library not found: '{library_id}'",
            {"library_id": library_id, "library_type": library_type},
        )
        self.library_id = library_id
        self.library_type = library_type


class SymbolNotFoundError(CircuitWeaverError):
    """Raised when a KiCad symbol cannot be found."""

    def __init__(self, symbol_id: str):
        super().__init__(
            f"Symbol not found: '{symbol_id}'",
            {"symbol_id": symbol_id},
        )
        self.symbol_id = symbol_id

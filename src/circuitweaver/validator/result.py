"""Validation result types."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationMessage:
    """A single validation message (error or warning)."""

    rule: str
    message: str
    element_id: str | None = None
    location: dict[str, Any] | None = None

    def __str__(self) -> str:
        parts = [f"[{self.rule}]"]
        if self.element_id:
            parts.append(f"({self.element_id})")
        parts.append(self.message)
        if self.location:
            loc_str = ", ".join(f"{k}={v}" for k, v in self.location.items())
            parts.append(f"at {loc_str}")
        return " ".join(parts)


@dataclass
class ValidationResult:
    """Result of validating a Circuit JSON file."""

    errors: list[ValidationMessage] = field(default_factory=list)
    warnings: list[ValidationMessage] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Check if validation passed (no errors)."""
        return len(self.errors) == 0

    def add_error(
        self,
        rule: str,
        message: str,
        element_id: str | None = None,
        location: dict[str, Any] | None = None,
    ) -> None:
        """Add an error to the result."""
        self.errors.append(ValidationMessage(rule, message, element_id, location))

    def add_warning(
        self,
        rule: str,
        message: str,
        element_id: str | None = None,
        location: dict[str, Any] | None = None,
    ) -> None:
        """Add a warning to the result."""
        self.warnings.append(ValidationMessage(rule, message, element_id, location))

    def merge(self, other: "ValidationResult") -> None:
        """Merge another validation result into this one."""
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "is_valid": self.is_valid,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": [
                {
                    "rule": e.rule,
                    "message": e.message,
                    "element_id": e.element_id,
                    "location": e.location,
                }
                for e in self.errors
            ],
            "warnings": [
                {
                    "rule": w.rule,
                    "message": w.message,
                    "element_id": w.element_id,
                    "location": w.location,
                }
                for w in self.warnings
            ],
        }

"""Base class for validation rules."""

from abc import ABC, abstractmethod
from typing import Any

from circuitweaver.types.circuit_json import CircuitElement
from circuitweaver.validator.result import ValidationResult


class ValidationRule(ABC):
    """Base class for all validation rules.

    Each rule is responsible for checking one aspect of the Circuit JSON
    and reporting any errors or warnings found.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Rule identifier used in error messages."""
        ...

    @property
    def description(self) -> str:
        """Human-readable description of what this rule checks."""
        return ""

    @abstractmethod
    def validate(
        self,
        elements: list[CircuitElement],
        context: dict[str, Any],
    ) -> ValidationResult:
        """Validate elements according to this rule.

        Args:
            elements: List of all circuit elements.
            context: Pre-computed context with indexed elements.

        Returns:
            ValidationResult with any errors or warnings found.
        """
        ...

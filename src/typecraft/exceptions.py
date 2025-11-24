"""
Exception classes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .converting.converter import BaseConversionFrame

__all__ = [
    "ValidationError",
    "SerializationError",
]


@dataclass
class ConversionErrorDetail:
    """
    Details about a single conversion error.
    """

    obj: Any
    """
    The object attempted to be converted.
    """

    frame: BaseConversionFrame
    """
    The frame in which the error was encountered.
    """

    exception: Exception
    """
    The exception encountered.
    """


class BaseConversionError(Exception):
    """
    Aggregated conversion errors encountered during validation or serialization.
    Collects all conversion errors found during processing and formats them in a
    Pydantic-style error display with paths to each error.
    """

    errors: list[ConversionErrorDetail]

    _action: str

    def __init__(self, errors: list[ConversionErrorDetail]):
        assert errors
        self.errors = errors
        super().__init__(self.__format_errors())

    def __format_errors(self) -> str:
        """
        Format all errors in a readable format with paths.
        """
        plural = "s" if len(self.errors) > 1 else ""
        lines = [f"Error{plural} occurred during {self._action}:"]

        for detail in self.errors:
            path = self.format_path(detail.frame.path)
            lines.append(
                '{}: "{}": {} -> {}'.format(
                    path,
                    detail.obj,
                    detail.frame.source_annotation.raw,
                    detail.frame.target_annotation.raw,
                )
            )
            lines += [f"  {m}" for m in str(detail.exception).splitlines()]

        return "\n".join(lines)

    @staticmethod
    def format_path(path: tuple[str | int, ...]) -> str:
        """
        Format a path tuple into Pydantic-style dot notation.

        Examples:

        - `('items', 1, 'value') -> "items[1].value"`
        - `('user', 'name') -> "user.name"`
        - `(0, 'id') -> "[0].id"`
        - `() -> "<root>"`
        """
        if not path:
            return "<root>"
        parts: list[str] = []
        for i, segment in enumerate(path):
            if isinstance(segment, int):
                # index: append as [n]
                parts.append(f"[{segment}]")
            else:
                # field name: prefix with dot
                prefix = "." if i != 0 else ""
                parts.append(f"{prefix}{segment}")
        return "".join(parts)


class ValidationError(BaseConversionError):
    """
    Aggregated conversion errors encountered during validation.
    """

    _action = "validation"


class SerializationError(BaseConversionError):
    """
    Aggregated conversion errors encountered during serialization.
    """

    _action = "serialization"

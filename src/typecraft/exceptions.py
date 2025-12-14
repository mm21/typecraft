"""
Exception classes.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generator

if TYPE_CHECKING:
    from .converting.converter import BaseConversionFrame

__all__ = [
    "ValidationError",
    "SerializationError",
    "ConversionErrorDetail",
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

    exc: Exception
    """
    The exception encountered.
    """

    @property
    def path(self) -> str:
        """
        Path tuple formatted as Pydantic-style dot notation.

        Examples:

        - `('items', 1, 'value') -> "items[1].value"`
        - `('user', 'name') -> "user.name"`
        - `(0, 'id') -> "[0].id"`
        - `() -> "<root>"`
        """
        if not self.frame.path:
            return "<root>"
        parts: list[str] = []
        for i, segment in enumerate(self.frame.path):
            if isinstance(segment, int):
                # index: append as [n]
                parts.append(f"[{segment}]")
            else:
                # field name: prefix with dot
                prefix = "." if i != 0 else ""
                parts.append(f"{prefix}{segment}")
        return "".join(parts)

    def format_error(self) -> Generator[str, None, None]:
        """
        Format this error for display.
        """
        if isinstance(self.exc, ExtraFieldError):
            # extra field: simplified output
            yield f"{self.path}: Unknown field"
            return

        # summary of conversion and exception name
        yield "{}: {}: {} -> {}: {}".format(
            self.path,
            self.obj,
            self.frame.source_annotation.raw,
            self.frame.target_annotation.raw,
            type(self.exc).__name__,
        )
        # details from the exception string
        yield from (f"  {m}" for m in str(self.exc).splitlines())
        # traceback for debugging in the case of assertion
        if isinstance(self.exc, AssertionError):
            yield from traceback.format_exception(self.exc)

    def _bubble_frame(self, path: str) -> ConversionErrorDetail:
        """
        Adjust frame upon bubbling up error to parent model.
        """
        return ConversionErrorDetail(
            self.obj, self.frame._copy(path_prepend=path), self.exc
        )


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

        for error in self.errors:
            lines += list(error.format_error())

        return "\n".join(lines)


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


class ExtraFieldError(Exception):
    """
    Captures an extra field when model's configuration has extra="forbid".
    """

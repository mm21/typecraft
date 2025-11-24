"""
Types used throughout subpackage.
"""

__all__ = [
    "ErrorSentinel",
    "ERROR_SENTINEL",
]


class ErrorSentinel:
    def __repr__(self) -> str:
        return type(self).__name__


ERROR_SENTINEL = ErrorSentinel()

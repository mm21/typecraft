"""
Common converters used in testcases.
"""

from typing import Any

from typecraft.converting.validator import TypeValidator


def _validate_int(obj: str | bytes | bytearray) -> int:
    return int(obj, 0)


INT_VALIDATOR = TypeValidator(str | bytes | bytearray, int, func=_validate_int)
STR_VALIDATOR = TypeValidator(Any, str)
FLOAT_VALIDATOR = TypeValidator(Any, float)

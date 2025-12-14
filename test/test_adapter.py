"""
Test `Adapter`.
"""

from typecraft.adapter import Adapter
from typecraft.validating import (
    ValidationParams,
)


def test_basic():
    adapter = Adapter(int)

    # validate with conversion
    result = adapter.validate("123", params=ValidationParams(strict=False))
    assert result == 123

    # serialize
    result = adapter.serialize(123)
    assert result == 123

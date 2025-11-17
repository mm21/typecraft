"""
Test `Adapter`.
"""

from typecraft.adapter import Adapter
from typecraft.validating import (
    ValidationParams,
)


def test_basic():
    adapter = Adapter(int, validation_params=ValidationParams(strict=False))

    # validate with conversion
    result = adapter.validate("123")
    assert result == 123

    # serialize
    result = adapter.serialize(123)
    assert result == 123

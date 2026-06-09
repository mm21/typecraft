"""
Test `Adapter`.
"""

from typecraft.adapter import Adapter


def test_basic():
    adapter = Adapter(int)

    # validate with conversion
    result = adapter.validate("123", strict=False)
    assert result == 123

    # serialize
    result = adapter.serialize(123)
    assert result == 123

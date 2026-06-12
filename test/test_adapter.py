"""
Test `Adapter`.
"""

from typecraft.adapter import Adapter
from typecraft.converting.builtin_converters import IntConverter
from typecraft.validating import TypeValidatorRegistry


def test_basic():
    # validate with conversion (explicit IntConverter needed since coercion is opt-in)
    adapter = Adapter(
        int, validator_registry=TypeValidatorRegistry(IntConverter.as_validator())
    )
    result = adapter.validate("123")
    assert result == 123

    # serialize
    result = adapter.serialize(123)
    assert result == 123

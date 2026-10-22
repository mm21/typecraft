"""
Test `Adapter`.
"""

from typecraft.adapter import Adapter
from typecraft.validating import TypeValidatorRegistry

from .converters import INT_VALIDATOR


def test_basic():
    # validate with conversion (explicit IntConverter needed since coercion is opt-in)
    adapter = Adapter(int, validator_registry=TypeValidatorRegistry(INT_VALIDATOR))
    validated = adapter.validate("123")
    assert validated == 123

    # serialize
    serialized = adapter.serialize(123)
    assert serialized == 123

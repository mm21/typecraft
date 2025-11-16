"""
Test adapting module functionality.
"""

from pytest import raises

from typecraft.adapting import Adapter, BaseAdapter
from typecraft.serializing import SerializationFrame, SerializerRegistry, serialize
from typecraft.validating import (
    ValidationFrame,
    ValidationParams,
    ValidatorRegistry,
    validate,
)


class MyClass:
    """
    A custom class which isn't natively serializable.
    """

    val: int

    def __init__(self, val: int):
        self.val = val


class BasicAdapter(BaseAdapter[int, MyClass]):
    """
    Adapter for values stored as int but serialized as str.
    """

    @classmethod
    def validate(cls, obj: int, _: ValidationFrame) -> MyClass:
        return MyClass(obj)

    @classmethod
    def serialize(cls, obj: MyClass, _: SerializationFrame) -> int:
        return obj.val


class RangeAdapter(BaseAdapter[list[int], range]):
    """
    Adapter for range objects serialized as (start, stop) list.
    """

    @classmethod
    def can_validate(cls, obj: list[int], *_) -> bool:
        return len(obj) == 2

    @classmethod
    def validate(cls, obj: list[int], _: ValidationFrame) -> range:
        """
        Validate list to range.
        """
        start, stop = obj
        return range(start, stop)

    @classmethod
    def serialize(cls, obj: range, _: SerializationFrame) -> list[int]:
        """
        Serialize range to list.
        """
        return [obj.start, obj.stop]


def test_adapter():
    """
    Test `Adapter`.
    """
    adapter = Adapter(int, validation_params=ValidationParams(strict=False))

    # validate
    result = adapter.validate("123")
    assert result == 123

    # serialize
    result = adapter.serialize(123)
    assert result == 123


def test_base_adapter():
    """
    Test BaseAdapter subclasses.
    """
    validator = BasicAdapter.as_validator()
    serializer = BasicAdapter.as_serializer()

    assert validator.source_annotation.raw is int
    assert validator.target_annotation.raw is MyClass
    assert serializer.source_annotation.raw is MyClass
    assert serializer.target_annotation.raw is int

    adapter = Adapter(
        MyClass,
        validator_registry=ValidatorRegistry(validator),
        serializer_registry=SerializerRegistry(serializer),
    )

    # make sure we get an exception without the adapter
    with raises(ValueError, match="could not be converted"):
        _ = validate(123, MyClass)
    with raises(ValueError, match="could not be converted"):
        _ = serialize(MyClass(321))

    result = adapter.validate(123)
    assert isinstance(result, MyClass)
    assert result.val == 123

    result = adapter.serialize(MyClass(321))
    assert isinstance(result, int)
    assert result == 321


def test_range_adapter():
    """
    Test range adapter for more complex types.
    """
    validator = RangeAdapter.as_validator()
    serializer = RangeAdapter.as_serializer()
    adapter = Adapter(
        range,
        validator_registry=ValidatorRegistry(validator),
        serializer_registry=SerializerRegistry(serializer),
    )

    result = adapter.validate([0, 10])
    assert isinstance(result, range)
    assert result == range(0, 10)

    result = adapter.serialize(range(0, 10))
    assert isinstance(result, list)
    assert result == [0, 10]

    # make sure we can't validate non-matching objects
    with raises(ValueError, match="could not be converted"):
        _ = adapter.validate([0, 10, 2])

    with raises(ValueError, match="could not be converted"):
        _ = adapter.validate([0, "10"])

    with raises(ValueError, match="could not be converted"):
        _ = adapter.validate((0, 10))

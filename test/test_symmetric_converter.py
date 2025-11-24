"""
Test `BaseSymmetricConverter`.
"""

from pytest import raises

from typecraft.adapter import Adapter
from typecraft.converting.symmetric_converter import BaseSymmetricConverter
from typecraft.exceptions import SerializationError, ValidationError
from typecraft.serializing import SerializationFrame, SerializerRegistry, serialize
from typecraft.validating import (
    ValidationFrame,
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

    def __repr__(self) -> str:
        return f"MyClass(val={self.val})"


class BasicConverter(BaseSymmetricConverter[int, MyClass]):
    """
    Adapter for values stored as int but serialized as str.
    """

    @classmethod
    def validate(cls, obj: int, _: ValidationFrame) -> MyClass:
        return MyClass(obj)

    @classmethod
    def serialize(cls, obj: MyClass, _: SerializationFrame) -> int:
        return obj.val


class RangeConverter(BaseSymmetricConverter[list[int], range]):
    """
    Adapter for range objects serialized as (start, stop, step) list or any other
    overloads of `range()`.
    """

    @classmethod
    def can_validate(cls, obj: list[int], *_) -> bool:
        return len(obj) in range(1, 4)

    @classmethod
    def validate(cls, obj: list[int], _: ValidationFrame) -> range:
        """
        Validate list to range.
        """
        return range(*obj)

    @classmethod
    def serialize(cls, obj: range, _: SerializationFrame) -> list[int]:
        """
        Serialize range to list.
        """
        return [obj.start, obj.stop, obj.step]


def test_basic():
    """
    Test basic `BaseSymmetricConverter` subclass.
    """
    validator = BasicConverter.as_validator()
    serializer = BasicConverter.as_serializer()

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
    with raises(ValidationError) as exc_info:
        _ = validate(123, MyClass)

    assert (
        str(exc_info.value)
        == """\
Error occurred during validation:
<root>: "123": <class 'int'> -> <class 'test.test_symmetric_converter.MyClass'>
  No matching converters"""
    )

    with raises(SerializationError) as exc_info:
        _ = serialize(MyClass(321))

    assert (
        str(exc_info.value)
        == """\
Error occurred during serialization:
<root>: "MyClass(val=321)": <class 'test.test_symmetric_converter.MyClass'> -> str | int | float | bool | None | list[JsonSerializableType] | dict[str | int | float | bool, JsonSerializableType]
  Errors during union member conversion:
    <class 'str'>: No matching converters
    <class 'int'>: No matching converters
    <class 'float'>: No matching converters
    <class 'bool'>: No matching converters
    <class 'NoneType'>: No matching converters
    list[JsonSerializableType]: No matching converters
    dict[str | int | float | bool, JsonSerializableType]: No matching converters"""
    )

    result = adapter.validate(123)
    assert isinstance(result, MyClass)
    assert result.val == 123

    result = adapter.serialize(MyClass(321))
    assert isinstance(result, int)
    assert result == 321


def test_range():
    """
    Test range converter for more complex types.
    """
    validator = RangeConverter.as_validator()
    serializer = RangeConverter.as_serializer()
    adapter = Adapter(
        range,
        validator_registry=ValidatorRegistry(validator),
        serializer_registry=SerializerRegistry(serializer),
    )

    result = adapter.validate([10])
    assert isinstance(result, range)
    assert result == range(0, 10)

    result = adapter.serialize(range(10))
    assert isinstance(result, list)
    assert result == [0, 10, 1]

    # make sure we can't validate non-matching objects
    with raises(ValidationError, match="No matching converters"):
        _ = adapter.validate([0, 10, 2, 1])

    with raises(ValidationError, match="No matching converters"):
        _ = adapter.validate([0, "10"])

    with raises(ValidationError, match="No matching converters"):
        _ = adapter.validate((0, 10))

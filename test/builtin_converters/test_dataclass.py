"""
Tests for dataclass symmetric converter.
"""

from dataclasses import dataclass

from pytest import raises

from typecraft.adapter import Adapter
from typecraft.converting.builtin_converters import DataclassConverter
from typecraft.converting.serializer import SerializationParams
from typecraft.converting.validator import ValidationParams
from typecraft.exceptions import SerializationError, ValidationError
from typecraft.serializing import TypeSerializerRegistry, serialize
from typecraft.validating import TypeValidatorRegistry, validate


@dataclass
class SimpleDataclass:
    """
    Simple dataclass for testing.
    """

    name: str
    age: int


@dataclass
class DataclassWithDefaults:
    """
    Dataclass with default values.
    """

    name: str
    age: int = 0


@dataclass
class NestedDataclass:
    """
    Dataclass containing another dataclass.
    """

    person: SimpleDataclass
    location: str


@dataclass
class DataclassWithList:
    """
    Dataclass with list field.
    """

    name: str
    tags: list[str]


def test_simple_dataclass():
    """
    Test basic dataclass validation and serialization.
    """
    validation_params = ValidationParams(use_builtin_validators=False)
    serialization_params = SerializationParams(use_builtin_serializers=False)
    adapter = Adapter(
        SimpleDataclass,
        validator_registry=TypeValidatorRegistry(DataclassConverter.as_validator()),
        serializer_registry=TypeSerializerRegistry(DataclassConverter.as_serializer()),
    )

    test_serialized = {"name": "Alice", "age": 30}
    test_validated = SimpleDataclass(name="Alice", age=30)

    # make sure we get an exception without the adapter
    with raises(ValidationError):
        _ = validate(test_serialized, SimpleDataclass, params=validation_params)

    with raises(SerializationError):
        _ = serialize(test_validated, params=serialization_params)

    # test validation
    validated = adapter.validate(test_serialized, params=validation_params)
    assert isinstance(validated, SimpleDataclass)
    assert validated.name == test_validated.name
    assert validated.age == test_validated.age

    # test serialization
    serialized = adapter.serialize(test_validated, params=serialization_params)
    assert isinstance(serialized, dict)
    assert serialized == test_serialized

    # test roundtrip with builtin converter
    assert validate(test_serialized, SimpleDataclass) == test_validated
    assert serialize(test_validated) == test_serialized

    # test invalid
    with raises(ValidationError):
        _ = validate("not-a-dict", SimpleDataclass)


def test_dataclass_with_defaults():
    """
    Test dataclass with default values.
    """
    adapter = Adapter(
        DataclassWithDefaults,
        validator_registry=TypeValidatorRegistry(DataclassConverter.as_validator()),
        serializer_registry=TypeSerializerRegistry(DataclassConverter.as_serializer()),
    )

    # test with all fields provided
    test_serialized = {"name": "Alice", "age": 30}
    test_validated = DataclassWithDefaults(name="Alice", age=30)

    validated = adapter.validate(test_serialized)
    assert isinstance(validated, DataclassWithDefaults)
    assert validated.name == test_validated.name
    assert validated.age == test_validated.age

    serialized = adapter.serialize(test_validated)
    assert serialized == test_serialized

    # test with defaults
    test_serialized_defaults = {"name": "Bob"}
    validated = adapter.validate(test_serialized_defaults)
    assert isinstance(validated, DataclassWithDefaults)
    assert validated.name == "Bob"
    assert validated.age == 0


def test_missing_required_field():
    """
    Test that missing required field raises ValueError.
    """
    adapter = Adapter(
        SimpleDataclass,
        validator_registry=TypeValidatorRegistry(DataclassConverter.as_validator()),
    )

    # missing 'age' field
    with raises(ValidationError):
        _ = adapter.validate({"name": "Alice"})


def test_nested():
    """
    Test nested dataclass validation and serialization.
    """
    adapter = Adapter(
        NestedDataclass,
        validator_registry=TypeValidatorRegistry(DataclassConverter.as_validator()),
        serializer_registry=TypeSerializerRegistry(DataclassConverter.as_serializer()),
    )

    test_serialized = {"person": {"name": "Alice", "age": 30}, "location": "NYC"}
    test_validated = NestedDataclass(
        person=SimpleDataclass(name="Alice", age=30), location="NYC"
    )

    # test validation
    validated = adapter.validate(test_serialized)
    assert isinstance(validated, NestedDataclass)
    assert isinstance(validated.person, SimpleDataclass)
    assert validated.person.name == test_validated.person.name
    assert validated.person.age == test_validated.person.age
    assert validated.location == test_validated.location

    # test serialization
    serialized = adapter.serialize(test_validated)
    assert isinstance(serialized, dict)
    assert serialized == test_serialized


def test_dataclass_with_list():
    """
    Test dataclass with list field.
    """
    adapter = Adapter(
        DataclassWithList,
        validator_registry=TypeValidatorRegistry(DataclassConverter.as_validator()),
        serializer_registry=TypeSerializerRegistry(DataclassConverter.as_serializer()),
    )

    test_serialized = {"name": "Project", "tags": ["python", "testing", "ci"]}
    test_validated = DataclassWithList(name="Project", tags=["python", "testing", "ci"])

    # test validation
    validated = adapter.validate(test_serialized)
    assert isinstance(validated, DataclassWithList)
    assert validated.name == test_validated.name
    assert validated.tags == test_validated.tags

    # test serialization
    serialized = adapter.serialize(test_validated)
    assert serialized == test_serialized


def test_invalid():
    """
    Test that invalid input fails validation and corrupted model fails serialization.
    """
    adapter = Adapter(
        SimpleDataclass,
        validator_registry=TypeValidatorRegistry(DataclassConverter.as_validator()),
    )

    class NonSerializable:
        def __repr__(self) -> str:
            return type(self).__name__

    test_serialized = {"person": {"name": "Alice", "age": "30"}, "location": 123}
    test_validated = NestedDataclass(
        person=SimpleDataclass(name="Alice", age=NonSerializable()), location="NYC"  # type: ignore
    )

    with raises(ValidationError) as exc_info:
        _ = validate(test_serialized, NestedDataclass)

    assert len(exc_info.value.errors) == 2
    assert (
        str(exc_info.value)
        == """\
2 validation errors for NestedDataclass
person.age=30: str -> int: TypeError
  No matching converters
location=123: int -> str: TypeError
  No matching converters"""
    )

    with raises(SerializationError) as exc_info:
        _ = serialize(test_validated)

    # list input should fail
    with raises(ValidationError, match="No matching converters"):
        _ = adapter.validate([{"name": "Alice", "age": 30}])

    # string input should fail
    with raises(ValidationError, match="No matching converters"):
        _ = adapter.validate("not a dict")

    # tuple input should fail
    with raises(ValidationError, match="No matching converters"):
        _ = adapter.validate(("Alice", 30))

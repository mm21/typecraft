"""
Tests for dataclass symmetric converter.
"""

from dataclasses import dataclass

from pytest import raises

from typecraft.adapter import Adapter
from typecraft.builtin_converters import DataclassConverter
from typecraft.serializing import SerializerRegistry, serialize
from typecraft.validating import ValidatorRegistry, validate


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
    adapter = Adapter(
        SimpleDataclass,
        validator_registry=ValidatorRegistry(DataclassConverter.as_validator()),
        serializer_registry=SerializerRegistry(DataclassConverter.as_serializer()),
    )

    test_serialized = {"name": "Alice", "age": 30}
    test_validated = SimpleDataclass(name="Alice", age=30)

    # make sure we get an exception without the adapter
    with raises(ValueError, match="could not be converted"):
        _ = validate(test_serialized, SimpleDataclass)
    with raises(ValueError, match="could not be converted"):
        _ = serialize(test_validated)

    # test validation
    validated = adapter.validate(test_serialized)
    assert isinstance(validated, SimpleDataclass)
    assert validated.name == test_validated.name
    assert validated.age == test_validated.age

    # test serialization
    serialized = adapter.serialize(test_validated)
    assert isinstance(serialized, dict)
    assert serialized == test_serialized


def test_dataclass_with_defaults():
    """
    Test dataclass with default values.
    """
    adapter = Adapter(
        DataclassWithDefaults,
        validator_registry=ValidatorRegistry(DataclassConverter.as_validator()),
        serializer_registry=SerializerRegistry(DataclassConverter.as_serializer()),
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
    Test that missing required fields raise ValueError.
    """
    adapter = Adapter(
        SimpleDataclass,
        validator_registry=ValidatorRegistry(DataclassConverter.as_validator()),
    )

    # missing 'age' field
    with raises(ValueError, match="missing 1 required positional argument: 'age'"):
        _ = adapter.validate({"name": "Alice"})

    # missing 'name' field
    with raises(ValueError, match="missing 1 required positional argument: 'name'"):
        _ = adapter.validate({"age": 30})


def test_nested():
    """
    Test nested dataclass validation and serialization.
    """
    adapter = Adapter(
        NestedDataclass,
        validator_registry=ValidatorRegistry(DataclassConverter.as_validator()),
        serializer_registry=SerializerRegistry(DataclassConverter.as_serializer()),
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
        validator_registry=ValidatorRegistry(DataclassConverter.as_validator()),
        serializer_registry=SerializerRegistry(DataclassConverter.as_serializer()),
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
    Test that non-dict input fails validation.
    """
    adapter = Adapter(
        SimpleDataclass,
        validator_registry=ValidatorRegistry(DataclassConverter.as_validator()),
    )

    # list input should fail
    with raises(ValueError, match="could not be converted"):
        _ = adapter.validate([{"name": "Alice", "age": 30}])

    # string input should fail
    with raises(ValueError, match="could not be converted"):
        _ = adapter.validate("not a dict")

    # tuple input should fail
    with raises(ValueError, match="could not be converted"):
        _ = adapter.validate(("Alice", 30))

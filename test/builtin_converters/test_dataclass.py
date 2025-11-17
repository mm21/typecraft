"""
Tests for dataclass symmetric converter.
"""

from dataclasses import dataclass
from datetime import date

from pytest import raises

from typecraft.adapter import Adapter
from typecraft.builtin_converters import DataclassConverter, DateConverter
from typecraft.inspecting.annotations import Annotation
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
    active: bool = True


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


@dataclass
class DataclassWithOptional:
    """
    Dataclass with optional field.
    """

    name: str
    nickname: str | None = None


@dataclass
class ComplexDataclass:
    """
    Complex nested dataclass with multiple types.
    """

    id: int
    person: SimpleDataclass
    tags: list[str]
    metadata: dict[str, int]
    birth_date: date | None = None


def test_simple_dataclass():
    """
    Test basic dataclass validation and serialization.
    """

    validator = DataclassConverter.as_validator()

    obj = {"name": "Alice", "age": 30}
    assert validator._check_convert(
        obj,
        source_annotation=Annotation(dict),
        target_annotation=Annotation(SimpleDataclass),
    )

    adapter = Adapter(
        SimpleDataclass,
        validator_registry=ValidatorRegistry(DataclassConverter.as_validator()),
        serializer_registry=SerializerRegistry(DataclassConverter.as_serializer()),
    )

    # make sure we get an exception without the adapter
    with raises(ValueError, match="could not be converted"):
        _ = validate({"name": "Alice", "age": 30}, SimpleDataclass)
    with raises(ValueError, match="could not be converted"):
        _ = serialize(SimpleDataclass(name="Alice", age=30))

    # test validation
    result = adapter.validate({"name": "Alice", "age": 30})
    assert isinstance(result, SimpleDataclass)
    assert result.name == "Alice"
    assert result.age == 30

    # test serialization
    result = adapter.serialize(SimpleDataclass(name="Bob", age=25))
    assert isinstance(result, dict)
    assert result == {"name": "Bob", "age": 25}


def test_dataclass_with_defaults():
    """
    Test dataclass with default values.
    """
    adapter = Adapter(
        DataclassWithDefaults,
        validator_registry=ValidatorRegistry(DataclassConverter.as_validator()),
        serializer_registry=SerializerRegistry(DataclassConverter.as_serializer()),
    )

    # test validation with all fields provided
    result = adapter.validate({"name": "Alice", "age": 30, "active": False})
    assert isinstance(result, DataclassWithDefaults)
    assert result.name == "Alice"
    assert result.age == 30
    assert result.active is False

    # test validation with defaults
    result = adapter.validate({"name": "Bob"})
    assert isinstance(result, DataclassWithDefaults)
    assert result.name == "Bob"
    assert result.age == 0
    assert result.active is True

    # test validation with partial defaults
    result = adapter.validate({"name": "Charlie", "age": 35})
    assert isinstance(result, DataclassWithDefaults)
    assert result.name == "Charlie"
    assert result.age == 35
    assert result.active is True

    # test serialization includes all fields
    result = adapter.serialize(DataclassWithDefaults(name="Dave", age=40, active=False))
    assert result == {"name": "Dave", "age": 40, "active": False}


def test_missing_required_field():
    """
    Test that missing required fields raise ValueError.
    """
    adapter = Adapter(
        SimpleDataclass,
        validator_registry=ValidatorRegistry(DataclassConverter.as_validator()),
    )

    # missing 'age' field
    with raises(ValueError, match="Missing required field 'age'"):
        _ = adapter.validate({"name": "Alice"})

    # missing 'name' field
    with raises(ValueError, match="Missing required field 'name'"):
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

    # test validation with nested dict
    result = adapter.validate(
        {"person": {"name": "Alice", "age": 30}, "location": "NYC"}
    )
    assert isinstance(result, NestedDataclass)
    assert isinstance(result.person, SimpleDataclass)
    assert result.person.name == "Alice"
    assert result.person.age == 30
    assert result.location == "NYC"

    # test serialization with nested dataclass
    person = SimpleDataclass(name="Bob", age=25)
    nested = NestedDataclass(person=person, location="SF")
    result = adapter.serialize(nested)
    assert isinstance(result, dict)
    assert result == {"person": {"name": "Bob", "age": 25}, "location": "SF"}


def test_dataclass_with_list():
    """
    Test dataclass with list field.
    """
    adapter = Adapter(
        DataclassWithList,
        validator_registry=ValidatorRegistry(DataclassConverter.as_validator()),
        serializer_registry=SerializerRegistry(DataclassConverter.as_serializer()),
    )

    # test validation
    result = adapter.validate({"name": "Project", "tags": ["python", "testing", "ci"]})
    assert isinstance(result, DataclassWithList)
    assert result.name == "Project"
    assert result.tags == ["python", "testing", "ci"]

    # test serialization
    result = adapter.serialize(
        DataclassWithList(name="Project", tags=["python", "testing"])
    )
    assert result == {"name": "Project", "tags": ["python", "testing"]}


def test_dataclass_with_optional():
    """
    Test dataclass with optional field.
    """
    adapter = Adapter(
        DataclassWithOptional,
        validator_registry=ValidatorRegistry(DataclassConverter.as_validator()),
        serializer_registry=SerializerRegistry(DataclassConverter.as_serializer()),
    )

    # test validation with optional field provided
    result = adapter.validate({"name": "Alice", "nickname": "Ally"})
    assert isinstance(result, DataclassWithOptional)
    assert result.name == "Alice"
    assert result.nickname == "Ally"

    # test validation with optional field omitted
    result = adapter.validate({"name": "Bob"})
    assert isinstance(result, DataclassWithOptional)
    assert result.name == "Bob"
    assert result.nickname is None

    # test validation with optional field as None
    result = adapter.validate({"name": "Charlie", "nickname": None})
    assert isinstance(result, DataclassWithOptional)
    assert result.name == "Charlie"
    assert result.nickname is None

    # test serialization with optional field
    result = adapter.serialize(DataclassWithOptional(name="Dave", nickname="D"))
    assert result == {"name": "Dave", "nickname": "D"}

    # test serialization without optional field
    result = adapter.serialize(DataclassWithOptional(name="Eve"))
    assert result == {"name": "Eve", "nickname": None}


def test_complex_nested_dataclass():
    """
    Test complex dataclass with multiple nested types.
    """
    adapter = Adapter(
        ComplexDataclass,
        validator_registry=ValidatorRegistry(
            DataclassConverter.as_validator(), DateConverter.as_validator()
        ),
        serializer_registry=SerializerRegistry(
            DataclassConverter.as_serializer(), DateConverter.as_serializer()
        ),
    )

    # test validation
    input_data = {
        "id": 123,
        "person": {"name": "Alice", "age": 30},
        "tags": ["python", "dataclass"],
        "metadata": {"score": 100, "rank": 1},
        "birth_date": "1993-05-15",
    }
    result = adapter.validate(input_data)
    assert isinstance(result, ComplexDataclass)
    assert result.id == 123
    assert isinstance(result.person, SimpleDataclass)
    assert result.person.name == "Alice"
    assert result.person.age == 30
    assert result.tags == ["python", "dataclass"]
    assert result.metadata == {"score": 100, "rank": 1}
    assert isinstance(result.birth_date, date)
    assert result.birth_date == date(1993, 5, 15)

    # test validation without optional birth_date
    input_data_no_date = {
        "id": 456,
        "person": {"name": "Bob", "age": 25},
        "tags": ["testing"],
        "metadata": {"score": 90},
    }
    result = adapter.validate(input_data_no_date)
    assert isinstance(result, ComplexDataclass)
    assert result.id == 456
    assert result.birth_date is None

    # test serialization
    person = SimpleDataclass(name="Charlie", age=35)
    complex_obj = ComplexDataclass(
        id=789,
        person=person,
        tags=["advanced", "typing"],
        metadata={"level": 5},
        birth_date=date(1988, 11, 20),
    )
    result = adapter.serialize(complex_obj)
    assert isinstance(result, dict)
    assert result == {
        "id": 789,
        "person": {"name": "Charlie", "age": 35},
        "tags": ["advanced", "typing"],
        "metadata": {"level": 5},
        "birth_date": "1988-11-20",
    }


def test_round_trip():
    """
    Test that dataclass round-trips correctly.
    """
    adapter = Adapter(
        SimpleDataclass,
        validator_registry=ValidatorRegistry(DataclassConverter.as_validator()),
        serializer_registry=SerializerRegistry(DataclassConverter.as_serializer()),
    )

    # original dataclass
    original = SimpleDataclass(name="TestUser", age=42)

    # serialize to dict
    serialized = adapter.serialize(original)
    assert isinstance(serialized, dict)

    # validate back to dataclass
    validated = adapter.validate(serialized)
    assert isinstance(validated, SimpleDataclass)
    assert validated.name == original.name
    assert validated.age == original.age


def test_invalid():
    """
    Test that non-dict input fails validation.
    """
    validator = DataclassConverter.as_validator()
    adapter = Adapter(
        SimpleDataclass,
        validator_registry=ValidatorRegistry(validator),
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

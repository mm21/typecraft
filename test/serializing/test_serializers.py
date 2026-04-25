"""
Test end-to-end serialization via APIs.
"""

from dataclasses import dataclass
from typing import Annotated, Any

from pytest import raises

from typecraft.converting.serializer import PlainSerializer
from typecraft.exceptions import SerializationError
from typecraft.inspecting.annotations import Annotation
from typecraft.serializing import (
    BaseGenericTypeSerializer,
    SerializationEngine,
    SerializationFrame,
    SerializationParams,
    TypeSerializer,
    serialize,
)


@dataclass
class Person:
    name: str
    age: int


@dataclass
class Company:
    name: str
    employees: list[Person]


def serialize_company(c: Company) -> dict[str, Any]:
    return {"name": c.name, "employees": c.employees}


PERSON_SERIALIZER = TypeSerializer(
    Person, dict, func=lambda p: {"name": p.name, "age": p.age}
)
COMPANY_SERIALIZER = TypeSerializer.from_func(serialize_company)


def test_custom_serializer():
    """
    Test with custom serializers for dataclasses.
    """

    person = Person(name="Alice", age=30)

    result = serialize(person, PERSON_SERIALIZER)
    assert result == {"name": "Alice", "age": 30}

    result = serialize(person, PERSON_SERIALIZER, source_type=Person)
    assert result == {"name": "Alice", "age": 30}


def test_nested_custom_serializer():
    """
    Test serialization with nested custom objects.
    """

    def serialize_company(c: Company, frame: SerializationFrame) -> dict:
        # use frame to recursively serialize employees
        return {
            "name": c.name,
            "employees": [
                frame.recurse(emp, i, source_annotation=Annotation(Person))
                for i, emp in enumerate(c.employees)
            ],
        }

    company_serializer = TypeSerializer.from_func(serialize_company)

    person1 = Person(name="Alice", age=30)
    person2 = Person(name="Bob", age=25)
    company = Company(name="TechCo", employees=[person1, person2])

    result = serialize(company, PERSON_SERIALIZER, company_serializer)
    assert result == {
        "name": "TechCo",
        "employees": [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}],
    }

    data = {
        "alice": Person(name="Alice", age=30),
        "bob": Person(name="Bob", age=25),
    }

    result = serialize(data, PERSON_SERIALIZER)
    assert result == {
        "alice": {"name": "Alice", "age": 30},
        "bob": {"name": "Bob", "age": 25},
    }

    data = {
        "team_a": [Person("Alice", 30), Person("Bob", 25)],
        "team_b": [Person("Charlie", 35)],
    }

    result = serialize(data, PERSON_SERIALIZER)

    assert result == {
        "team_a": [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}],
        "team_b": [{"name": "Charlie", "age": 35}],
    }


def test_list():
    """
    Test serializing a list of custom objects.
    """

    people = [
        Person(name="Alice", age=30),
        Person(name="Bob", age=25),
    ]

    result = serialize(people, PERSON_SERIALIZER)
    assert result == [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25},
    ]


def test_union_types():
    """
    Test serialization with union types.
    """

    person = Person(name="Alice", age=30)

    # int | Person where object is int
    result = serialize(42, PERSON_SERIALIZER, source_type=int | Person)
    assert result == 42

    # int | Person where object is Person
    result = serialize(person, PERSON_SERIALIZER, source_type=int | Person)
    assert result == {"name": "Alice", "age": 30}


def test_subclass():
    """
    Test subclass of BaseGenericSerializer.
    """

    class MySerializer(BaseGenericTypeSerializer[int, str]):
        def convert(self, obj: int, frame: SerializationFrame) -> str:
            _ = frame
            return str(obj)

    serializer = MySerializer()
    obj = 123

    assert serializer.check_match(Annotation(int), Annotation(str))
    assert serializer.can_convert(obj, Annotation(int), Annotation(str))
    conv_obj = serializer.convert(obj, _create_frame(int, str))
    assert conv_obj == "123"


def test_plain():
    """
    Test plain serializers.
    """

    def plain_serialize_before(val: object, frame: SerializationFrame) -> list[Any]:
        _ = frame
        assert isinstance(val, set)
        # reverse the values so we know this serializer kicked in
        return sorted(val, reverse=True)

    before_serializer = PlainSerializer(plain_serialize_before, mode="before")

    # without before serializer: raises error since we didn't get a list
    with raises(SerializationError) as exc_info:
        _ = serialize({1, 2, 3}, source_type=list[int])

    assert (
        str(exc_info.value)
        == """\
1 serialization error for list[int]
<root>={1, 2, 3}: list[int] -> str | int | float | bool | None | list[JsonSerializableType] | dict[str | int | float | bool, JsonSerializableType]: ValueError
  Object "{1, 2, 3}" is not an instance of Annotation(list[int], extras=(), concrete_type=<class 'list'>)"""
    )

    # with before serializer: no error since before serializer converted to a list
    obj = serialize({1, 2, 3}, source_type=Annotated[list[int], before_serializer])

    assert obj == [3, 2, 1]

    def plain_serialize_after(val: list[int]) -> list[int]:
        assert isinstance(val, list)
        return sorted(val, reverse=True)

    after_serializer = PlainSerializer(plain_serialize_after)

    # without after serializer: list doesn't get reversed
    obj = serialize([1, 2, 3])
    assert obj == [1, 2, 3]

    # with after serializer: list gets sorted
    obj = serialize([1, 2, 3], source_type=Annotated[list[int], after_serializer])
    assert obj == [3, 2, 1]


def _create_frame(
    source_annotation: Any,
    target_annotation: Any,
    params: SerializationParams | None = None,
) -> SerializationFrame:
    return SerializationEngine().create_frame(
        source_annotation=Annotation(source_annotation),
        target_annotation=Annotation(target_annotation),
        params=params or SerializationParams(sort_sets=True),
        context=None,
    )

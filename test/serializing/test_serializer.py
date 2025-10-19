"""
Test end-to-end serialization via APIs.
"""

from dataclasses import dataclass

from modelingkit.inspecting.annotations import Annotation
from modelingkit.serializing import (
    SerializationContext,
    TypedSerializer,
    TypedSerializerRegistry,
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


def test_custom_serializer():
    """
    Test with custom serializers for dataclasses.
    """

    def serialize_person(p: Person) -> dict:
        return {"name": p.name, "age": p.age}

    person = Person(name="Alice", age=30)
    serializer = TypedSerializer(Person, func=serialize_person)

    result = serialize(person, Person, serializer)
    assert result == {"name": "Alice", "age": 30}

    result = serialize(person, Person | None, serializer)
    assert result == {"name": "Alice", "age": 30}


def test_nested_custom_serializer():
    """
    Test serialization with nested custom objects.
    """

    def serialize_person(p: Person) -> dict:
        return {"name": p.name, "age": p.age}

    def serialize_company(
        c: Company, annotation: Annotation, context: SerializationContext
    ) -> dict:
        # use context to recursively serialize employees
        return {
            "name": c.name,
            "employees": [context.serialize(emp, Person) for emp in c.employees],
        }

    person1 = Person(name="Alice", age=30)
    person2 = Person(name="Bob", age=25)
    company = Company(name="TechCo", employees=[person1, person2])

    person_serializer = TypedSerializer(Person, func=serialize_person)
    company_serializer = TypedSerializer(Company, func=serialize_company)

    result = serialize(company, Company, person_serializer, company_serializer)
    assert result == {
        "name": "TechCo",
        "employees": [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}],
    }


def test_list_of_custom_objects():
    """
    Test serializing a list of custom objects.
    """

    def serialize_person(p: Person) -> dict:
        return {"name": p.name, "age": p.age}

    people = [
        Person(name="Alice", age=30),
        Person(name="Bob", age=25),
    ]

    serializer = TypedSerializer(Person, func=serialize_person)
    result = serialize(people, list[Person], serializer)

    assert result == [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25},
    ]


def test_union_types():
    """
    Test serialization with union types.
    """

    def serialize_person(p: Person) -> dict:
        return {"name": p.name, "age": p.age, "type": "person"}

    person = Person(name="Alice", age=30)
    serializer = TypedSerializer(Person, func=serialize_person)

    # int | Person where object is int
    result = serialize(42, int | Person, serializer)
    assert result == 42

    # int | Person where object is Person
    result = serialize(person, int | Person, serializer)
    assert result == {"name": "Alice", "age": 30, "type": "person"}


def test_dict_with_custom_values():
    """
    Test dict with custom object values.
    """

    def serialize_person(p: Person) -> dict:
        return {"name": p.name, "age": p.age}

    people_dict = {
        "alice": Person(name="Alice", age=30),
        "bob": Person(name="Bob", age=25),
    }

    serializer = TypedSerializer(Person, func=serialize_person)
    result = serialize(people_dict, dict[str, Person], serializer)

    assert result == {
        "alice": {"name": "Alice", "age": 30},
        "bob": {"name": "Bob", "age": 25},
    }


def test_mixed_nested_structures():
    """
    Test complex nested structures with custom objects.
    """

    def serialize_person(p: Person) -> dict:
        return {"name": p.name, "age": p.age}

    # dict[str, list[Person]]
    data = {
        "team_a": [Person("Alice", 30), Person("Bob", 25)],
        "team_b": [Person("Charlie", 35)],
    }

    serializer = TypedSerializer(Person, func=serialize_person)
    result = serialize(data, dict[str, list[Person]], serializer)

    assert result == {
        "team_a": [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}],
        "team_b": [{"name": "Charlie", "age": 35}],
    }


def test_custom_serializer_for_builtin():
    """
    Test that custom serializers work for builtin types.
    """
    # int -> str
    serializer = TypedSerializer(int, func=str)
    assert serialize(42, int, serializer) == "42"

    # float -> int (truncate)
    def truncate(f: float) -> int:
        return int(f)

    serializer = TypedSerializer(float, func=truncate)
    assert serialize(3.14, float, serializer) == 3
    assert serialize(2.99, float, serializer) == 2

    # str -> uppercase
    def uppercase(s: str) -> str:
        return s.upper()

    serializer = TypedSerializer(str, func=uppercase)
    assert serialize("hello", str, serializer) == "HELLO"


def test_custom_serializer_for_builtin_collections():
    """
    Test that custom serializers work for builtin collection types.
    """

    # list -> sorted list
    def sort_list(lst: list) -> list:
        return sorted(lst)

    serializer = TypedSerializer(list, func=sort_list)
    assert serialize([3, 1, 2], list, serializer) == [1, 2, 3]

    # dict -> keys only
    def dict_keys(d: dict) -> list:
        return list(d.keys())

    serializer = TypedSerializer(dict, func=dict_keys)
    assert serialize({"b": 2, "a": 1}, dict, serializer) == ["b", "a"]


def test_registry():
    """
    Test serialization with registry.
    """
    registry = TypedSerializerRegistry()
    registry.register(TypedSerializer(int, func=str))

    obj = 1
    result = serialize(obj, int, registry)
    assert result == "1"

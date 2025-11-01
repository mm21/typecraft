"""
Test end-to-end serialization via APIs.
"""

from dataclasses import dataclass

from typecraft.inspecting.annotations import Annotation
from typecraft.serializing import (
    SerializationHandle,
    Serializer,
    SerializerRegistry,
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
    serializer = Serializer(Person, func=serialize_person)

    result = serialize(person, serializer)
    assert result == {"name": "Alice", "age": 30}

    result = serialize(person, serializer, source_type=Person | None)
    assert result == {"name": "Alice", "age": 30}


def test_nested_custom_serializer():
    """
    Test serialization with nested custom objects.
    """

    def serialize_person(p: Person) -> dict:
        return {"name": p.name, "age": p.age}

    def serialize_company(c: Company, handle: SerializationHandle) -> dict:
        # use context to recursively serialize employees
        return {
            "name": c.name,
            "employees": [
                handle.recurse(emp, i, Annotation(Person))
                for i, emp in enumerate(c.employees)
            ],
        }

    person1 = Person(name="Alice", age=30)
    person2 = Person(name="Bob", age=25)
    company = Company(name="TechCo", employees=[person1, person2])

    person_serializer = Serializer(Person, func=serialize_person)
    company_serializer = Serializer(Company, func=serialize_company)

    result = serialize(company, person_serializer, company_serializer)
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

    serializer = Serializer(Person, func=serialize_person)
    result = serialize(people, serializer)

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
    serializer = Serializer(Person, func=serialize_person)

    # int | Person where object is int
    result = serialize(42, serializer, source_type=int | Person)
    assert result == 42

    # int | Person where object is Person
    result = serialize(person, serializer, source_type=int | Person)
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

    serializer = Serializer(Person, func=serialize_person)
    result = serialize(people_dict, serializer)

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

    serializer = Serializer(Person, func=serialize_person)
    result = serialize(data, serializer)

    assert result == {
        "team_a": [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}],
        "team_b": [{"name": "Charlie", "age": 35}],
    }


def test_custom_serializer_for_builtin():
    """
    Test that custom serializers work for builtin types.
    """
    # int -> str
    serializer = Serializer(int, str)
    assert serialize(42, serializer) == "42"

    # float -> int (truncate)
    def truncate(f: float) -> int:
        return int(f)

    serializer = Serializer(float, func=truncate)
    assert serialize(3.14, serializer) == 3
    assert serialize(2.99, serializer) == 2

    # str -> uppercase
    def uppercase(s: str) -> str:
        return s.upper()

    serializer = Serializer(str, func=uppercase)
    assert serialize("hello", serializer) == "HELLO"


def test_custom_serializer_for_builtin_collections():
    """
    Test that custom serializers work for builtin collection types.
    """

    # list -> sorted list
    def sort_list(lst: list) -> list:
        return sorted(lst)

    serializer = Serializer(list, func=sort_list)
    assert serialize([3, 1, 2], serializer) == [1, 2, 3]

    # dict -> keys only
    def dict_keys(d: dict) -> list:
        return list(d.keys())

    serializer = Serializer(dict, func=dict_keys)
    assert serialize({"b": 2, "a": 1}, serializer) == ["b", "a"]


def test_registry():
    """
    Test serialization with registry.
    """
    registry = SerializerRegistry()
    registry.register(Serializer(int, str))

    obj = 1
    result = serialize(obj, registry)
    assert result == "1"

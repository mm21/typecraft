"""
Test end-to-end serialization via APIs.
"""

from dataclasses import dataclass
from typing import Any

from typecraft.inspecting.annotations import Annotation
from typecraft.serializing import (
    SerializationFrame,
    Serializer,
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


PERSON_SERIALIZER = Serializer(
    Person, dict, func=lambda p: {"name": p.name, "age": p.age}
)
COMPANY_SERIALIZER = Serializer.from_func(serialize_company)


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

    company_serializer = Serializer.from_func(serialize_company)

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

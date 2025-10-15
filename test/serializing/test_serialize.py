"""
Test end-to-end serialization via APIs.
"""

from dataclasses import dataclass
from typing import Literal

from modelingkit.serializing import TypedSerializer, serialize


@dataclass
class Person:
    name: str
    age: int


@dataclass
class Company:
    name: str
    employees: list[Person]


def test_primitives():
    """
    Test serialization of primitives.
    """
    assert serialize(42) == 42
    assert serialize(42, int) == 42
    assert serialize(3.14, float) == 3.14
    assert serialize("hello", str) == "hello"
    assert serialize(True, bool) is True
    assert serialize(None) is None
    assert serialize(None, None) is None


def test_builtin_collections():
    """
    Test serialization of builtin collections without custom serializers.
    """
    # list
    assert serialize([1, 2, 3]) == [1, 2, 3]
    assert serialize([1, 2, 3], list[int]) == [1, 2, 3]

    # tuple -> list
    assert serialize((1, 2, 3)) == [1, 2, 3]
    assert serialize((1, 2, 3), tuple[int, ...]) == [1, 2, 3]

    # set -> list (order may vary)
    result = serialize({1, 2, 3})
    assert isinstance(result, list)
    assert set(result) == {1, 2, 3}

    result = serialize({1, 2, 3}, set[int])
    assert isinstance(result, list)
    assert set(result) == {1, 2, 3}

    # frozenset -> list
    result = serialize(frozenset([1, 2, 3]))
    assert isinstance(result, list)
    assert set(result) == {1, 2, 3}

    # dict
    assert serialize({"a": 1, "b": 2}) == {"a": 1, "b": 2}
    assert serialize({"a": 1, "b": 2}, dict[str, int]) == {"a": 1, "b": 2}


def test_nested_collections():
    """
    Test serialization of nested collections.
    """
    # list[list[int]]
    obj = [[1, 2], [3, 4]]
    assert serialize(obj) == [[1, 2], [3, 4]]
    assert serialize(obj, list[list[int]]) == [[1, 2], [3, 4]]

    # dict[str, list[int]]
    obj = {"a": [1, 2], "b": [3, 4]}
    assert serialize(obj) == {"a": [1, 2], "b": [3, 4]}
    assert serialize(obj, dict[str, list[int]]) == {"a": [1, 2], "b": [3, 4]}

    # list[tuple[int, str]]
    obj = [(1, "a"), (2, "b")]
    assert serialize(obj) == [[1, "a"], [2, "b"]]


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

    # also works without explicit type hint
    result = serialize(person, None, serializer)
    assert result == {"name": "Alice", "age": 30}


def test_nested_custom_serializer():
    """
    Test serialization with nested custom objects.
    """

    def serialize_person(p: Person) -> dict:
        return {"name": p.name, "age": p.age}

    def serialize_company(c: Company, annotation, context) -> dict:
        # Use context to recursively serialize employees
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


def test_no_annotation():
    """
    Test serialization without specific annotation (type inference).
    """
    # primitives should work
    assert serialize(42) == 42
    assert serialize("hello") == "hello"

    # collections should work
    assert serialize([1, 2, 3]) == [1, 2, 3]
    assert serialize({"a": 1}) == {"a": 1}


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


def test_literal_values():
    """
    Test serialization of literal types (should pass through).
    """
    assert serialize("active", Literal["active", "inactive"]) == "active"
    assert serialize(42, Literal[42, 43, 44]) == 42


def test_range_and_generator():
    """
    Test serialization of range and generators.
    """
    # range -> list
    result = serialize(range(5))
    assert result == [0, 1, 2, 3, 4]

    # generator -> list
    def gen():
        for i in range(3):
            yield i * 2

    result = serialize(gen())
    assert result == [0, 2, 4]


def test_empty_collections():
    """
    Test serialization of empty collections.
    """
    assert serialize([]) == []
    assert serialize({}) == {}
    assert serialize(set()) == []
    assert serialize((), tuple[int, ...]) == []


def test_without_serializer():
    """
    Test that objects without serializers pass through.
    """

    class CustomClass:
        def __init__(self, value):
            self.value = value

    obj = CustomClass(42)
    result = serialize(obj)
    assert result is obj  # passed through unchanged

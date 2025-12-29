"""
Test end-to-end serialization via APIs.
"""

from typing import Literal

from typecraft.serializing import TypeSerializer, serialize


def test_primitives():
    """
    Test serialization of primitives.
    """
    assert serialize(42) == 42
    assert serialize(42, source_type=int) == 42
    assert serialize(3.14, source_type=float) == 3.14
    assert serialize("hello", source_type=str) == "hello"
    assert serialize(True, source_type=bool) is True
    assert serialize(None, source_type=type(None)) is None
    assert serialize(None, source_type=None) is None


def test_builtin_collections():
    """
    Test serialization of builtin collections without custom serializers.
    """
    # list
    assert serialize([1, 2, 3]) == [1, 2, 3]
    assert serialize([1, 2, 3], source_type=list[int]) == [1, 2, 3]

    # tuple -> list (with Ellipsis)
    assert serialize((1, 2, 3)) == [1, 2, 3]
    assert serialize((1, 2, 3), source_type=tuple[int, ...]) == [1, 2, 3]

    # tuple -> list (fixed length)
    assert serialize((1, 2, 3), source_type=tuple[int, int, int]) == [1, 2, 3]
    assert serialize((1, "a"), source_type=tuple[int, str]) == [1, "a"]

    # set -> list (order may vary)
    result = serialize({1, 2, 3})
    assert isinstance(result, list)
    assert set(result) == {1, 2, 3}

    result = serialize({1, 2, 3}, source_type=set[int])
    assert isinstance(result, list)
    assert set(result) == {1, 2, 3}

    # frozenset -> list
    result = serialize(frozenset([1, 2, 3]))
    assert isinstance(result, list)
    assert set(result) == {1, 2, 3}

    # dict
    assert serialize({"a": 1, "b": 2}) == {"a": 1, "b": 2}
    assert serialize({"a": 1, "b": 2}, source_type=dict[str, int]) == {"a": 1, "b": 2}


def test_nested_collections():
    """
    Test serialization of nested collections.
    """
    # list[list[int]]
    obj = [[1, 2], [3, 4]]
    assert serialize(obj) == [[1, 2], [3, 4]]
    assert serialize(obj, source_type=list[list[int]]) == [[1, 2], [3, 4]]

    # dict[str, list[int]]
    obj = {"a": [1, 2], "b": [3, 4]}
    assert serialize(obj) == {"a": [1, 2], "b": [3, 4]}
    assert serialize(obj, source_type=dict[str, list[int]]) == {
        "a": [1, 2],
        "b": [3, 4],
    }

    # list[tuple[int, str]]
    obj = [(1, "a"), (2, "b")]
    assert serialize(obj, source_type=list[tuple[int, str]]) == [[1, "a"], [2, "b"]]


def test_literal_values():
    """
    Test serialization of literal types (should pass through).
    """
    assert serialize("active", source_type=Literal["active", "inactive"]) == "active"
    assert serialize(42, source_type=Literal[42, 43, 44]) == 42


def test_empty_collections():
    """
    Test serialization of empty collections.
    """
    assert serialize([]) == []
    assert serialize([], source_type=list[int]) == []
    assert serialize({}) == {}
    assert serialize(set()) == []
    assert serialize(()) == []


def test_fixed_length_tuples():
    """
    Test serialization of fixed-length tuples with specific type for each element.
    """
    # homogeneous fixed-length tuple
    assert serialize((1, 2, 3)) == [1, 2, 3]

    # heterogeneous fixed-length tuple
    assert serialize((1, "a", 3.14)) == [1, "a", 3.14]
    assert serialize((42, "hello")) == [42, "hello"]

    # nested tuples
    assert serialize(((1, 2), (3, 4))) == [
        [1, 2],
        [3, 4],
    ]


def test_custom():
    """
    Test that custom objects can be serialized.
    """

    class CustomClass:
        value: int

        def __init__(self, value: int):
            self.value = value

    obj = CustomClass(42)
    serializer = TypeSerializer(CustomClass, int, func=lambda obj: obj.value)
    result = serialize(obj, serializer)
    assert result == 42

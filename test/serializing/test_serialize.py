"""
Test end-to-end serialization via APIs.
"""

from typing import Any, Literal

from modelingkit.serializing import serialize


def test_primitives():
    """
    Test serialization of primitives.
    """
    assert serialize(42, int) == 42
    assert serialize(42, int) == 42
    assert serialize(3.14, float) == 3.14
    assert serialize("hello", str) == "hello"
    assert serialize(True, bool) is True
    assert serialize(None, type(None)) is None
    assert serialize(None, None) is None


def test_builtin_collections():
    """
    Test serialization of builtin collections without custom serializers.
    """
    # list
    assert serialize([1, 2, 3], list[int]) == [1, 2, 3]
    assert serialize([1, 2, 3], list[int]) == [1, 2, 3]

    # tuple -> list (with Ellipsis)
    assert serialize((1, 2, 3), tuple[int, ...]) == [1, 2, 3]
    assert serialize((1, 2, 3), tuple[int, ...]) == [1, 2, 3]

    # tuple -> list (fixed length)
    assert serialize((1, 2, 3), tuple[int, int, int]) == [1, 2, 3]
    assert serialize((1, "a"), tuple[int, str]) == [1, "a"]

    # set -> list (order may vary)
    result = serialize({1, 2, 3}, set[int])
    assert isinstance(result, list)
    assert set(result) == {1, 2, 3}

    result = serialize({1, 2, 3}, set[int])
    assert isinstance(result, list)
    assert set(result) == {1, 2, 3}

    # frozenset -> list
    result = serialize(frozenset([1, 2, 3]), frozenset[int])
    assert isinstance(result, list)
    assert set(result) == {1, 2, 3}

    # dict
    assert serialize({"a": 1, "b": 2}, dict[str, int]) == {"a": 1, "b": 2}
    assert serialize({"a": 1, "b": 2}, dict[str, int]) == {"a": 1, "b": 2}


def test_nested_collections():
    """
    Test serialization of nested collections.
    """
    # list[list[int]]
    obj = [[1, 2], [3, 4]]
    assert serialize(obj, list[list[int]]) == [[1, 2], [3, 4]]
    assert serialize(obj, list[list[int]]) == [[1, 2], [3, 4]]

    # dict[str, list[int]]
    obj = {"a": [1, 2], "b": [3, 4]}
    assert serialize(obj, dict[str, list[int]]) == {"a": [1, 2], "b": [3, 4]}
    assert serialize(obj, dict[str, list[int]]) == {"a": [1, 2], "b": [3, 4]}

    # list[tuple[int, str]]
    obj = [(1, "a"), (2, "b")]
    assert serialize(obj, list[tuple[int, str]]) == [[1, "a"], [2, "b"]]


def test_any_annotation():
    """
    Test serialization with Any annotation (minimal type information).
    """
    # primitives should work
    assert serialize(42, Any) == 42
    assert serialize("hello", Any) == "hello"

    # collections should work
    assert serialize([1, 2, 3], Any) == [1, 2, 3]
    assert serialize({"a": 1}, Any) == {"a": 1}


def test_literal_values():
    """
    Test serialization of literal types (should pass through).
    """
    assert serialize("active", Literal["active", "inactive"]) == "active"
    assert serialize(42, Literal[42, 43, 44]) == 42


def test_empty_collections():
    """
    Test serialization of empty collections.
    """
    assert serialize([], list[int]) == []
    assert serialize({}, dict[str, int]) == {}
    assert serialize(set(), set[int]) == []
    assert serialize((), tuple[int, ...]) == []


def test_fixed_length_tuples():
    """
    Test serialization of fixed-length tuples with specific type for each element.
    """
    # homogeneous fixed-length tuple
    assert serialize((1, 2, 3), tuple[int, int, int]) == [1, 2, 3]

    # heterogeneous fixed-length tuple
    assert serialize((1, "a", 3.14), tuple[int, str, float]) == [1, "a", 3.14]
    assert serialize((42, "hello"), tuple[int, str]) == [42, "hello"]

    # nested tuples
    assert serialize(((1, 2), (3, 4)), tuple[tuple[int, int], tuple[int, int]]) == [
        [1, 2],
        [3, 4],
    ]


def test_without_serializer():
    """
    Test that objects without serializers pass through.
    """

    class CustomClass:
        def __init__(self, value):
            self.value = value

    obj = CustomClass(42)
    result = serialize(obj, CustomClass)
    assert result is obj  # passed through unchanged

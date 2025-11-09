"""
Test end-to-end validation via APIs.
"""

from types import NoneType
from typing import Annotated, Generator, Literal

from pytest import raises

from typecraft.validating import (
    Validator,
    ValidatorRegistry,
    normalize_to_list,
    validate,
)


class IntList(list[int]):
    """
    List subclass with int type parameter.
    """


class IntStrDict(dict[int, str]):
    """
    Dict subclass with int, str type parameters.
    """


def test_valid():
    """
    Test with no conversions: the validated type should be the same object as the
    input type.
    """

    # literal values
    assert validate(True, Literal[True]) is True
    assert validate(True, str | Literal[True]) is True
    assert validate(None, None) is None
    assert validate(None, NoneType) is None
    assert validate(None, int | None) is None
    assert validate("def", Literal["abc", "def", "ghi"]) == "def"

    # builtin list type
    obj = [0, 1, 2]
    result = validate(obj, list[int])
    assert result is obj


def test_invalid():
    """
    Test with no conversions: validation should raise an error.
    """

    with raises(ValueError):
        _ = validate("abc", Literal["def", "ghi"])

    with raises(ValueError):
        _ = validate(0, str | bool)


def test_conversion():

    # list[str | int] -> list[int]
    result = validate(["1", "2", 3], list[int], strict=False)
    assert result == [1, 2, 3]

    # list[tuple[str]] -> list[list[int]]
    obj = [("1", "2"), ("3", "4")]
    result = validate(obj, list[list[int]], strict=False)
    assert result == [[1, 2], [3, 4]]

    # list[str] -> tuple[int, str]
    obj = ["1", "2"]
    result = validate(obj, tuple[int, str], strict=False)
    assert result == (1, "2")

    # list[int] -> tuple[str, ...]
    obj = [1, 2]
    result = validate(obj, tuple[str, ...], strict=False)
    assert result == ("1", "2")

    # list[list[tuple[str, str]]] -> list[list[list[int]]]
    obj = [[("1", "2"), ("3", "4")], [("5", "6")]]
    result = validate(obj, list[list[list[int]]], strict=False)
    assert result == [[[1, 2], [3, 4]], [[5, 6]]]

    # dict[int, list[str]] -> dict[str, list[int]]
    obj = {1: ["1", "2"], 2: ["3", "4"]}
    result = validate(obj, dict[str, list[int]], strict=False)
    assert result == {"1": [1, 2], "2": [3, 4]}

    # list[int] -> set[str]
    obj = [1, 2, 3, 2, 1]
    result = validate(obj, set[str], strict=False)
    assert result == {"1", "2", "3"}

    # str -> int | float
    obj = "1.5"
    result = validate(obj, int | float, strict=False)
    assert result == 1.5

    # annotated type
    obj = ["1", "2", "3"]
    result = validate(
        obj,
        Annotated[list[int], "positive integers"],
        strict=False,
    )
    assert result == [1, 2, 3]

    # range -> list[int]
    obj = range(3)
    result = validate(obj, list[int], strict=False)
    assert result == [0, 1, 2]

    # generator -> list[int]
    def gen() -> Generator[int, None, None]:
        for i in range(3):
            yield i

    obj = gen()
    result = validate(obj, list[int], strict=False)
    assert result == [0, 1, 2]

    # generator -> tuple[int, int, int]
    obj = gen()
    result = validate(obj, tuple[int, int, int], strict=False)
    assert result == (0, 1, 2)


def test_collection_subclass():
    """
    Test subclass of list and dict with extraction of type param.
    """
    obj = IntList([0, 1, 2])
    result = validate(obj, IntList)
    assert result is obj

    with raises(
        ValueError, match=r"Object '2' \(<class 'str'>\) could not be converted"
    ):
        obj = IntList([0, 1, "2"])  # type: ignore
        _ = validate(obj, IntList)

    obj = IntStrDict({0: "a"})
    result = validate(obj, IntStrDict)
    assert result is obj


def test_generic_subclass():
    """
    Test generic subclasses of builtins.
    """

    class MyList[T](list[T]):
        pass

    class MyDict[K, V](dict[K, V]):
        pass

    # custom list type
    obj = MyList([0, 1, 2])
    result = validate(obj, MyList[int])
    assert result is obj

    result = validate(obj, list[int])
    assert result is obj

    # custom dict type
    obj = MyDict({0: "a"})
    result = validate(obj, MyDict[int, str])
    assert result is obj

    result = validate(obj, dict[int, str])
    assert result is obj


def test_registry():
    """
    Test validation with registry.
    """
    registry = ValidatorRegistry()
    registry.register(Validator(str, int))

    obj = "1"
    result = validate(obj, int, registry)
    assert result == 1


def test_normalize_to_list():
    """
    Verify normalizing to list.
    """

    obj1 = [1, 2, "3"]
    obj2 = 1

    norm_obj1 = normalize_to_list(obj1, str, strict=False)
    assert norm_obj1 == ["1", "2", "3"]

    norm_obj2 = normalize_to_list(obj2, str, strict=False)
    assert norm_obj2 == ["1"]

from types import NoneType
from typing import Annotated, Generator, Literal

from pytest import raises

from modelingkit.validating import Converter, validate_obj


def test_conversion():

    # test with and without explicit converters
    for converters in [(Converter(int, (str,)),), ()]:

        # list[str | int] -> list[int]
        result = validate_obj(["1", "2", 3], list[int], *converters, lenient=True)
        assert result == [1, 2, 3]

        # list[tuple[str]] -> list[list[int]]
        obj = [("1", "2"), ("3", "4")]
        result = validate_obj(obj, list[list[int]], *converters, lenient=True)
        assert result == [[1, 2], [3, 4]]

        # list[str] -> tuple[int, str]
        obj = ["1", "2"]
        result = validate_obj(obj, tuple[int, str], *converters, lenient=True)
        assert result == (1, "2")

        # list[int] -> tuple[str, ...]
        obj = [1, 2]
        result = validate_obj(obj, tuple[str, ...], *converters, lenient=True)
        assert result == ("1", "2")

        # list[list[tuple[str, str]]] -> list[list[list[int]]]
        obj = [[("1", "2"), ("3", "4")], [("5", "6")]]
        result = validate_obj(obj, list[list[list[int]]], *converters, lenient=True)
        assert result == [[[1, 2], [3, 4]], [[5, 6]]]

        # dict[int, list[str]] -> dict[str, list[int]]
        obj = {1: ["1", "2"], 2: ["3", "4"]}
        result = validate_obj(obj, dict[str, list[int]], *converters, lenient=True)
        assert result == {"1": [1, 2], "2": [3, 4]}

        # list[int] -> set[str]
        obj = [1, 2, 3, 2, 1]
        result = validate_obj(obj, set[str], *converters, lenient=True)
        assert result == {"1", "2", "3"}

        # str -> int | float
        obj = "1.5"
        result = validate_obj(obj, int | float, *converters, lenient=True)
        assert result == 1.5

        # annotated type
        obj = ["1", "2", "3"]
        result = validate_obj(
            obj,
            Annotated[list[int], "positive integers"],
            *converters,
            lenient=True,
        )
        assert result == [1, 2, 3]

        # range -> list[int]
        obj = range(3)
        result = validate_obj(obj, list[int], *converters, lenient=True)
        assert result == [0, 1, 2]

        # generator -> list[int]
        def gen() -> Generator[int, None, None]:
            for i in range(3):
                yield i

        obj = gen()
        result = validate_obj(obj, list[int], *converters, lenient=True)
        assert result == [0, 1, 2]

        # generator -> tuple[int, int, int]
        obj = gen()
        result = validate_obj(obj, tuple[int, int, int], *converters, lenient=True)
        assert result == (0, 1, 2)


def test_valid():
    """
    Test with no conversions: the validated type should be the same object as the
    input type.
    """

    # literal values
    assert validate_obj(True, Literal[True]) is True
    assert validate_obj(True, str | Literal[True]) is True
    assert validate_obj(None, None) is None
    assert validate_obj(None, NoneType) is None
    assert validate_obj(None, int | None) is None
    assert validate_obj("def", Literal["abc", "def", "ghi"]) == "def"

    # builtin list type
    obj = [0, 1, 2]
    result = validate_obj(obj, list[int])
    assert obj is result
    assert obj == result

    class MyList[T](list[T]):
        pass

    # custom list type
    obj = MyList([0, 1, 2])
    result = validate_obj(obj, MyList[int])
    assert obj is result
    assert obj == result

    # custom list type -> builtin list type, still satisfies type without conversion
    obj = MyList([0, 1, 2])
    result = validate_obj(obj, list[int])
    assert obj is result
    assert obj == result


def test_invalid():
    """
    Test with no conversions: validation should raise an error.
    """

    with raises(ValueError):
        _ = validate_obj("abc", Literal["def", "ghi"])

    with raises(ValueError):
        _ = validate_obj(0, str | bool)

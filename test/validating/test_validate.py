"""
Test end-to-end validation via APIs.
"""

from types import NoneType
from typing import Annotated, Generator, Literal

from pytest import raises

from typecraft.converting.builtin_converters import (
    LIST_VALIDATOR,
    SET_VALIDATOR,
    TUPLE_VALIDATOR,
)
from typecraft.exceptions import ValidationError
from typecraft.validating import (
    TypeValidator,
    normalize_to_list,
    validate,
)

from ..converters import FLOAT_VALIDATOR, INT_VALIDATOR, STR_VALIDATOR


class IntList(list[int]):
    """
    List subclass with int type parameter.
    """


class IntStrDict(dict[int, str]):
    """
    Dict subclass with int, str type parameters.
    """


class MyInt(int):
    pass


class MyList[T](list[T]):
    pass


class MyDict[K, V](dict[K, V]):
    pass


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

    with raises(ValidationError) as exc_info:
        _ = validate([1, 2, "3"], list[str | float])

    assert len(exc_info.value.errors) == 2
    assert (
        str(exc_info.value)
        == """\
2 validation errors for list[str | float]
[0]=1: int -> str | float: TypeError
  Errors during union member conversion:
    str: No matching converters
    float: No matching converters
[1]=2: int -> str | float: TypeError
  Errors during union member conversion:
    str: No matching converters
    float: No matching converters"""
    )

    # IntConverter is provided but "1.5" is not a valid integer in any base
    with raises(ValidationError) as exc_info:
        _ = validate(["1.5", "2.5"], list[int], INT_VALIDATOR)

    assert len(exc_info.value.errors) == 2
    assert (
        str(exc_info.value)
        == """\
2 validation errors for list[int]
[0]=1.5: str -> int: ValueError
  TypeValidator(str | bytes | bytearray[narrowable] -> int[!narrowable][widenable]) failed: invalid literal for int() with base 0: '1.5'
[1]=2.5: str -> int: ValueError
  TypeValidator(str | bytes | bytearray[narrowable] -> int[!narrowable][widenable]) failed: invalid literal for int() with base 0: '2.5'"""
    )

    with raises(ValidationError) as exc_info:
        _ = validate(0, str | bool)

    assert len(exc_info.value.errors) == 1
    assert (
        str(exc_info.value)
        == """\
1 validation error for str | bool
<root>=0: int -> str | bool: TypeError
  Errors during union member conversion:
    str: No matching converters
    bool: No matching converters"""
    )

    with raises(ValidationError) as exc_info:
        _ = validate("abc", Literal["def", "ghi"])

    assert len(exc_info.value.errors) == 1
    assert (
        str(exc_info.value)
        == """\
1 validation error for typing.Literal['def', 'ghi']
<root>=abc: str -> typing.Literal['def', 'ghi']: TypeError
  No matching converters"""
    )


def test_nested_invalid():
    """
    Test nested invalid types.
    """

    with raises(ValidationError) as exc_info:
        _ = validate([0, 1, 2], MyList[MyInt], TypeValidator(list, MyList))

    assert (
        str(exc_info.value)
        == """\
3 validation errors for test.validating.test_validate.MyList[test.validating.test_validate.MyInt]
[0]=0: int -> MyInt: TypeError
  No matching converters
[1]=1: int -> MyInt: TypeError
  No matching converters
[2]=2: int -> MyInt: TypeError
  No matching converters"""
    )


def test_conversion():

    # list[str | int] -> list[int]: str coerced to int via IntConverter
    result = validate(["1", "2", 3], list[int], INT_VALIDATOR)
    assert result == [1, 2, 3]

    # hex string via IntConverter (base-0 auto-detects 0x prefix)
    result = validate(["0xff", "0b11", "42"], list[int], INT_VALIDATOR)
    assert result == [255, 3, 42]

    # list[tuple[str]] -> list[list[int]]
    obj = [("1", "2"), ("3", "4")]
    result = validate(obj, list[list[int]], INT_VALIDATOR, LIST_VALIDATOR)
    assert result == [[1, 2], [3, 4]]

    # list[str] -> tuple[int, str]
    obj = ["1", "2"]
    result = validate(obj, tuple[int, str], INT_VALIDATOR, TUPLE_VALIDATOR)
    assert result == (1, "2")

    # list[int] -> tuple[str, ...]
    obj = [1, 2]
    result = validate(obj, tuple[str, ...], STR_VALIDATOR, TUPLE_VALIDATOR)
    assert result == ("1", "2")

    # list[list[tuple[str, str]]] -> list[list[list[int]]]
    obj = [[("1", "2"), ("3", "4")], [("5", "6")]]
    result = validate(
        obj,
        list[list[list[int]]],
        INT_VALIDATOR,
        LIST_VALIDATOR,
    )
    assert result == [[[1, 2], [3, 4]], [[5, 6]]]

    # dict[int, list[str]] -> dict[str, list[int]]
    obj = {1: ["1", "2"], 2: ["3", "4"]}
    result = validate(
        obj,
        dict[str, list[int]],
        INT_VALIDATOR,
        STR_VALIDATOR,
    )
    assert result == {"1": [1, 2], "2": [3, 4]}

    # list[int] -> set[str]
    obj = [1, 2, 3, 2, 1]
    result = validate(obj, set[str], STR_VALIDATOR, SET_VALIDATOR)
    assert result == {"1", "2", "3"}

    # str -> int | float  (IntConverter fails for "1.5", FloatConverter succeeds)
    obj = "1.5"
    result = validate(obj, int | float, FLOAT_VALIDATOR)
    assert result == 1.5

    # annotated type
    obj = ["1", "2", "3"]
    result = validate(
        obj,
        Annotated[list[int], "positive integers"],
        INT_VALIDATOR,
    )
    assert result == [1, 2, 3]

    # range -> list[int]
    obj = range(3)
    result = validate(obj, list[int], LIST_VALIDATOR)
    assert result == [0, 1, 2]

    # generator -> list[int]
    def gen() -> Generator[int, None, None]:
        for i in range(3):
            yield i

    obj = gen()
    result = validate(obj, list[int], LIST_VALIDATOR)
    assert result == [0, 1, 2]

    # generator -> tuple[int, int, int]
    obj = gen()
    result = validate(obj, tuple[int, int, int], TUPLE_VALIDATOR)
    assert result == (0, 1, 2)


def test_collection_subclass():
    """
    Test subclass of list and dict with extraction of type param.
    """
    obj = IntList([0, 1, 2])
    result = validate(obj, IntList)
    assert result is obj

    with raises(ValidationError) as exc_info:
        obj = IntList([0, 1, "2"])  # type: ignore
        _ = validate(obj, IntList)

    assert len(exc_info.value.errors) == 1
    assert (
        str(exc_info.value)
        == """\
1 validation error for IntList
[2]=2: str -> int: TypeError
  No matching converters"""
    )

    obj = [0, 1, 2]
    result = validate(obj, IntList, TypeValidator(list, IntList))
    assert isinstance(result, IntList)
    assert result == [0, 1, 2]

    obj = [0, 1, "2"]
    result = validate(
        obj,
        IntList,
        TypeValidator(list, IntList),
        INT_VALIDATOR,
    )
    assert isinstance(result, IntList)
    assert result == [0, 1, 2]

    obj = IntStrDict({0: "a"})
    result = validate(obj, IntStrDict)
    assert result is obj

    obj = {0: "a"}
    result = validate(obj, IntStrDict, TypeValidator(dict, IntStrDict))
    assert isinstance(result, IntStrDict)
    assert result == {0: "a"}

    obj = {"0": "a"}
    result = validate(
        obj,
        IntStrDict,
        TypeValidator(dict, IntStrDict),
        INT_VALIDATOR,
    )
    assert isinstance(result, IntStrDict)
    assert result == {0: "a"}


def test_generic_subclass():
    """
    Test generic subclasses of builtins.
    """

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


def test_normalize_to_list():
    """
    Verify normalizing to list.
    """

    obj1 = [1, 2, "3"]
    obj2 = 1

    norm_obj1 = normalize_to_list(obj1, str, STR_VALIDATOR)
    assert norm_obj1 == ["1", "2", "3"]

    norm_obj2 = normalize_to_list(obj2, str, STR_VALIDATOR)
    assert norm_obj2 == ["1"]

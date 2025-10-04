from typing import Annotated, Generator

from packagekit.modeling.validating import Converter, validate_obj


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

        # None -> None
        result = validate_obj(None, int | None, *converters, lenient=True)
        assert result is None


def test_valid():
    """
    Test with no conversions: the validated type should be the same object as the
    input type.
    """

    # builtin list type
    test_list = [0, 1, 2]
    validated_list = validate_obj(test_list, list[int])
    assert test_list is validated_list
    assert test_list == validated_list

    class MyList[T](list[T]):
        pass

    # custom list type
    test_list = MyList([0, 1, 2])
    validated_list = validate_obj(test_list, MyList[int])
    assert test_list is validated_list
    assert test_list == validated_list

    # custom list type -> builtin list type, still satisfies type without conversion
    test_list = MyList([0, 1, 2])
    validated_list = validate_obj(test_list, list[int])
    assert test_list is validated_list
    assert test_list == validated_list

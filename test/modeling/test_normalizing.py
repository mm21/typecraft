from typing import Annotated

from packagekit.modeling.normalizing import Converter, normalize_obj


def test_normalize():

    # test with and without explicit converters
    for converters in [(Converter(int, (str,)),), ()]:

        # list[str | int] -> list[int]
        result = normalize_obj(["1", "2", 3], list[int], *converters, lenient=True)
        assert result == [1, 2, 3]

        # list[tuple[str]] -> list[list[int]]
        obj = [("1", "2"), ("3", "4")]
        result = normalize_obj(obj, list[list[int]], *converters, lenient=True)
        assert result == [[1, 2], [3, 4]]

        # list[str] -> tuple[int, str]
        obj = ["1", "2"]
        result = normalize_obj(obj, tuple[int, str], *converters, lenient=True)
        assert result == (1, "2")

        # list[int] -> tuple[str, ...]
        obj = [1, 2]
        result = normalize_obj(obj, tuple[str, ...], *converters, lenient=True)
        assert result == ("1", "2")

        # list[list[tuple[str, str]]] -> list[list[list[int]]]
        obj = [[("1", "2"), ("3", "4")], [("5", "6")]]
        result = normalize_obj(obj, list[list[list[int]]], *converters, lenient=True)
        assert result == [[[1, 2], [3, 4]], [[5, 6]]]

        # dict[int, list[str]] -> dict[str, list[int]]
        obj = {1: ["1", "2"], 2: ["3", "4"]}
        result = normalize_obj(obj, dict[str, list[int]], *converters, lenient=True)
        assert result == {"1": [1, 2], "2": [3, 4]}

        # list[int] -> set[str]
        obj = [1, 2, 3, 2, 1]
        result = normalize_obj(obj, set[str], *converters, lenient=True)
        assert result == {"1", "2", "3"}

        # str -> int | float
        obj = "1.5"
        result = normalize_obj(obj, int | float, *converters, lenient=True)
        assert result == 1.5

        # annotated type
        obj = ["1", "2", "3"]
        result = normalize_obj(
            obj,
            Annotated[list[int], "positive integers"],
            *converters,
            lenient=True,
        )

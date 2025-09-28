from typing import Any

from pytest import raises

from packagekit.data.normalizer import Converter
from packagekit.modeling.dataclasses import BaseValidatedDataclass


class BasicTest(BaseValidatedDataclass):
    a: int = 123
    b: str = "abc"


class ConversionTest(BaseValidatedDataclass):
    a: int = 123
    b: str = "abc"

    def dataclass_converters(self) -> tuple[Converter[Any], ...]:
        return (Converter(int, (str,)),)


class UnionTest(BaseValidatedDataclass):
    a: int | str = 123


def test_basic():
    basic = BasicTest()

    with raises(ValueError):
        basic.a = "321"  # type: ignore

    basic.a = 321
    basic.b = "cba"
    assert basic.a, basic.b == (321, "cba")


def test_validation():
    with raises(TypeError):

        class _(BaseValidatedDataclass):
            a: int = 123
            b: str = "abc"

            @classmethod
            def dataclass_valid_types(cls) -> tuple[Any, ...]:
                return (int, bool)


def test_conversion():
    conversion = ConversionTest()
    conversion.a = "321"  # type: ignore


def test_union():
    union = UnionTest()
    assert union.a == 123

    union.a = "abc"
    assert union.a == "abc"

    with raises(ValueError):
        union.a = 123.0  # type: ignore

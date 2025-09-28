from dataclasses import dataclass
from typing import Any

from pytest import raises

from packagekit.data.normalizer import Converter
from packagekit.modeling.dataclasses import BaseValidatedDataclass


@dataclass
class BasicTest(BaseValidatedDataclass):
    a: int = 123
    b: str = "abc"


@dataclass
class ConversionTest(BaseValidatedDataclass):
    a: int = 123
    b: str = "abc"

    def dataclass_converters(self) -> tuple[Converter[Any]]:
        return (Converter(int, (str,)),)


class MissingDataclassTest(BaseValidatedDataclass):
    """
    Missing @dataclass decorator.
    """

    a: int = 123


def test_basic():
    basic = BasicTest()

    with raises(ValueError):
        basic.a = "321"  # type: ignore

    basic.a = 321
    basic.b = "cba"
    assert basic.a, basic.b == (321, "cba")


def test_conversion():
    conversion = ConversionTest()
    conversion.a = "321"  # type: ignore


def test_missing_dataclass():
    missing_dataclass = MissingDataclassTest()
    with raises(TypeError):
        missing_dataclass.a = 321

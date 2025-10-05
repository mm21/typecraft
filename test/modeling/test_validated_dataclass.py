from pytest import raises

from packagekit.modeling.validated_dataclass import (
    BaseValidatedDataclass,
    DataclassConfig,
)


class BasicTest(BaseValidatedDataclass):
    a: int = 123
    b: str = "abc"


class UnionTest(BaseValidatedDataclass):
    dataclass_config = DataclassConfig(validate_on_assignment=True)

    a: int | str = 123


class ValidateOnAssignmentTest(BaseValidatedDataclass):
    dataclass_config = DataclassConfig(validate_on_assignment=True)

    a: int = 123
    b: str = "abc"


class LenientTest(BaseValidatedDataclass):
    dataclass_config = DataclassConfig(lenient=True)

    a: int = 123
    b: str = "abc"


class NestedTest(BaseValidatedDataclass):
    basic: BasicTest
    union: UnionTest


def test_basic():
    basic = BasicTest()

    # not validated on assignment
    basic.a = "321"  # type: ignore

    basic.a = 321
    basic.b = "cba"
    assert basic.a, basic.b == (321, "cba")


def test_union():
    union = UnionTest()
    assert union.a == 123

    union.a = "abc"
    assert union.a == "abc"

    with raises(ValueError):
        union.a = 123.0  # type: ignore


def test_conversion():

    validate_on_assignment = ValidateOnAssignmentTest()

    with raises(ValueError):
        validate_on_assignment.a = "321"  # type: ignore

    lenient = LenientTest(a="321")  # type: ignore
    assert lenient.a == 321

    # not validated upon assignment
    lenient.a = "321"  # type: ignore
    assert lenient.a == "321"


def test_nested():

    # pass nested dataclasses
    _ = NestedTest(basic=BasicTest(), union=UnionTest())

    basic_dict = {"a": 321, "b": "cba"}
    union_dict = {"a": 321}
    nested_dict = {"basic": basic_dict, "union": union_dict}

    # pass dicts, will get converted to dataclasses
    nested = NestedTest(**nested_dict)
    assert nested.basic.a == 321
    assert nested.basic.b == "cba"
    assert nested.union.a == 321

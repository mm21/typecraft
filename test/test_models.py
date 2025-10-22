from typing import Any

from pytest import raises

from typecraft.models import (
    BaseModel,
    Field,
    FieldInfo,
    ModelConfig,
)


class BasicTest(BaseModel):
    a: int = 123
    b: str = "abc"


class UnionTest(BaseModel):
    model_config = ModelConfig(validate_on_assignment=True)

    a: int | str = 123


class ValidateOnAssignmentTest(BaseModel):
    model_config = ModelConfig(validate_on_assignment=True)

    a: int = 123
    b: str = "abc"


class LenientTest(BaseModel):
    model_config = ModelConfig(lenient=True)

    a: int = 123
    b: str = "abc"


class NestedTest(BaseModel):
    basic: BasicTest
    union: UnionTest


class PrePostValidateTest(BaseModel):
    a: int

    def model_pre_validate(self, field_info: FieldInfo, value: Any) -> Any:
        assert field_info.name == "a"
        return int(value)

    def model_post_validate(self, field_info: FieldInfo, value: Any) -> Any:
        assert field_info.name == "a"
        assert isinstance(value, int)
        assert value > 0
        return value


class LoadDumpTest(BaseModel):
    test_field: int = Field(alias="test-field")


def test_basic():
    dc = BasicTest()

    # not validated on assignment
    dc.a = "321"  # type: ignore

    dc.a = 321
    dc.b = "cba"
    assert dc.a, dc.b == (321, "cba")


def test_union():
    dc = UnionTest()
    assert dc.a == 123

    dc.a = "abc"
    assert dc.a == "abc"

    with raises(ValueError):
        dc.a = 123.0  # type: ignore


def test_conversion():
    dc = ValidateOnAssignmentTest()

    with raises(ValueError):
        dc.a = "321"  # type: ignore

    dc = LenientTest(a="321")  # type: ignore
    assert dc.a == 321

    # not validated upon assignment
    dc.a = "321"  # type: ignore
    assert dc.a == "321"


def test_nested():
    # pass nested dataclasses
    _ = NestedTest(basic=BasicTest(), union=UnionTest())

    basic_dict = {"a": 321, "b": "cba"}
    union_dict = {"a": 321}
    nested_dict = {"basic": basic_dict, "union": union_dict}

    # pass dicts, will get converted to dataclasses
    dc = NestedTest(**nested_dict)
    assert dc.basic.a == 321
    assert dc.basic.b == "cba"
    assert dc.union.a == 321

    dump = dc.model_dump()
    assert dump == nested_dict


def test_pre_post_validate():
    dc = PrePostValidateTest(a="123")  # type: ignore
    assert dc.a == 123

    with raises(AssertionError):
        _ = PrePostValidateTest(a=0)


def test_load_dump():

    # without alias
    dc = LoadDumpTest.model_load({"test_field": 123})
    assert dc.test_field == 123
    dump = dc.model_dump()
    assert dump["test_field"] == 123

    # with alias
    dc = LoadDumpTest.model_load({"test-field": 123}, by_alias=True)
    assert dc.test_field == 123
    dump = dc.model_dump(by_alias=True)
    assert dump["test-field"] == 123

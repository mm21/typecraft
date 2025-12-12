"""
Tests for decorator-based validator/serializer registration.
"""

from typing import Any

from pytest import raises

from typecraft.converting.serializer import Serializer
from typecraft.exceptions import ValidationError
from typecraft.model import (
    BaseModel,
    Field,
    FieldInfo,
    ModelConfig,
    field_serializer,
    field_validator,
    typed_serializers,
    typed_validators,
)
from typecraft.serializing import serialize
from typecraft.validating import ValidationParams, Validator, validate


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


class CoercionTest(BaseModel):
    model_config = ModelConfig(validation_params=ValidationParams(strict=False))

    a: int = 123
    b: str = "abc"


class NestedTest(BaseModel):
    basic: BasicTest
    union: UnionTest


class MyInt(int):
    """
    Custom integer for testing validators/serializers.
    """


class FieldValidatorTest(BaseModel):
    """
    Test field-level validators with decorator.
    """

    a: MyInt

    @field_validator
    def validate_a_before_1(self, obj: Any, field_info: FieldInfo) -> Any:
        """
        Demonstrate passing info and using an instance method.
        """
        assert isinstance(self, FieldValidatorTest)
        assert field_info.name == "a"
        return obj

    @field_validator("a", mode="before")
    @classmethod
    def validate_a_before_2(cls, obj: Any) -> Any:
        """
        Convert string to int before builtin validation.
        """
        assert issubclass(cls, FieldValidatorTest)
        if isinstance(obj, str):
            return MyInt(int(obj))
        return obj

    @field_validator("a", mode="after")
    @classmethod
    def validate_a_after(cls, obj: Any) -> Any:
        """
        Ensure value is positive after validation.
        """
        assert isinstance(obj, MyInt)
        assert obj > 0, "Value must be positive"
        return obj


class FieldValidatorAllFieldsTest(BaseModel):
    """
    Test field validators that apply to all fields.
    """

    a: int
    b: int

    @field_validator(mode="before")
    @classmethod
    def validate_all_before(cls, obj: Any, field: FieldInfo) -> Any:
        """
        Convert string to int for all fields.
        """
        if isinstance(obj, str):
            return int(obj)
        return obj

    @field_validator(mode="after")
    @classmethod
    def validate_all_after(cls, obj: Any, field: FieldInfo) -> Any:
        """
        Ensure all int values are positive.
        """
        if isinstance(obj, int):
            assert obj > 0, f"Field {field.name} must be positive"
        return obj


class FieldSerializerTest(BaseModel):
    """
    Test field-level serializer.
    """

    my_int: MyInt

    @field_serializer("my_int")
    def serialize_my_int(self, obj: MyInt) -> int:
        """
        Serialize MyInt back to int.
        """
        return int(obj)


class FieldSerializerAllFieldsTest(BaseModel):
    """
    Test field serializers that apply to all fields.
    """

    a: MyInt
    b: MyInt

    @field_serializer
    def serialize_all(self, obj: Any, field: FieldInfo) -> Any:
        """
        Serialize all MyInt fields back to int.
        """
        if isinstance(obj, MyInt):
            return int(obj)
        return obj


class TypedValidatorsTest(BaseModel):
    """
    Test typed validators via decorator.
    """

    my_int: MyInt

    @typed_validators
    @classmethod
    def validators(cls) -> tuple[Validator, ...]:
        return (
            Validator(
                int,
                MyInt,
                func=lambda obj: MyInt(obj),
            ),
        )


class TypedSerializersTest(BaseModel):
    """
    Test typed serializers via decorator.
    """

    my_int: MyInt

    @typed_serializers
    @classmethod
    def serializers(cls) -> tuple[Serializer, ...]:
        return (
            Serializer(
                MyInt,
                int,
                func=lambda obj: obj,
            ),
        )


class LoadDumpTest(BaseModel):
    test_field: int = Field(alias="test-field")


class MultipleFieldValidatorTest(BaseModel):
    """
    Test multiple validators on same field.
    """

    a: int

    @field_validator("a", mode="before")
    @classmethod
    def strip_whitespace(cls, obj: Any) -> Any:
        """
        Strip whitespace if string.
        """
        if isinstance(obj, str):
            return obj.strip()
        return obj

    @field_validator("a", mode="before")
    @classmethod
    def convert_to_int(cls, obj: Any) -> Any:
        """
        Convert string to int.
        """
        if isinstance(obj, str):
            return int(obj)
        return obj


class CombinedValidatorSerializerTest(BaseModel):
    """
    Test combining typed validators/serializers with field validators/serializers.
    """

    my_int: MyInt
    plain_int: int

    @typed_validators
    @classmethod
    def validators(cls) -> tuple[Validator[Any, Any], ...]:
        return (
            Validator(
                int,
                MyInt,
                func=lambda obj: MyInt(obj),
            ),
        )

    @typed_serializers
    @classmethod
    def serializers(cls) -> tuple[Serializer[Any, Any], ...]:
        return (
            Serializer(
                int,
                MyInt,
                func=lambda obj: obj.val,
            ),
        )

    @field_validator("plain_int", mode="before")
    @classmethod
    def validate_plain(cls, obj: Any) -> Any:
        """
        Convert string to int.
        """
        if isinstance(obj, str):
            return int(obj)
        return obj


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

    with raises(ValidationError):
        dc.a = 123.0  # type: ignore


def test_conversion():
    dc = ValidateOnAssignmentTest()

    with raises(ValidationError):
        dc.a = "321"  # type: ignore

    dc = CoercionTest(a="321")  # type: ignore
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


def test_field_validator():
    """
    Test @field_validator decorator with specific fields.
    """
    # string gets converted to int via before validator
    dc = FieldValidatorTest(a="123")  # type: ignore
    assert isinstance(dc.a, MyInt)
    assert dc.a == 123

    # after validator ensures positive
    with raises(AssertionError, match="Value must be positive"):
        _ = FieldValidatorTest(a=MyInt(0))


def test_field_validator_all_fields():
    """
    Test @field_validator decorator without field names (applies to all).
    """
    # both fields get string-to-int conversion
    dc = FieldValidatorAllFieldsTest(a="123", b="456")  # type: ignore
    assert dc.a == 123
    assert dc.b == 456

    # after validator ensures positive for all fields
    with raises(AssertionError, match="Field a must be positive"):
        _ = FieldValidatorAllFieldsTest(a=0, b=1)

    with raises(AssertionError, match="Field b must be positive"):
        _ = FieldValidatorAllFieldsTest(a=1, b=0)


def test_field_serializer():
    """
    Test @field_serializer decorator with specific fields.
    """
    dc = FieldSerializerTest(my_int=MyInt(123))
    assert isinstance(dc.my_int, MyInt)
    assert dc.my_int == 123

    dump = dc.model_dump()
    assert dump == {"my_int": 123}


def test_field_serializer_all_fields():
    """
    Test @field_serializer decorator without field names (applies to all).
    """
    dc = FieldSerializerAllFieldsTest(a=MyInt(123), b=MyInt(456))
    assert isinstance(dc.a, MyInt)
    assert isinstance(dc.b, MyInt)
    assert dc.a == 123
    assert dc.b == 456

    dump = dc.model_dump()
    assert dump == {"a": 123, "b": 456}


def test_typed_validators():
    """
    Test @typed_validators decorator.
    """
    dc = TypedValidatorsTest(my_int=123)  # type: ignore
    assert isinstance(dc.my_int, MyInt)
    assert dc.my_int == 123


def test_typed_serializers():
    """
    Test @typed_serializers decorator.
    """
    dc = TypedSerializersTest(my_int=MyInt(123))
    assert isinstance(dc.my_int, MyInt)
    assert dc.my_int == 123

    dump = dc.model_dump()
    assert dump == {"my_int": 123}


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


def test_list():
    obj = [{}, {"a": 321, "b": "cba"}]
    validated = validate(obj, list[BasicTest])

    assert len(validated) == 2
    assert all(isinstance(o, BasicTest) for o in validated)

    serialized = serialize(validated)
    assert serialized == [{"a": 123, "b": "abc"}, {"a": 321, "b": "cba"}]


def test_multiple_field_validators():
    """
    Test multiple validators on same field execute in order.
    """
    dc = MultipleFieldValidatorTest(a="  123  ")  # type: ignore
    assert dc.a == 123


def test_combined_validators_serializers():
    """
    Test combining typed and field-level validators/serializers.
    """
    dc = CombinedValidatorSerializerTest(my_int=123, plain_int="456")  # type: ignore
    assert isinstance(dc.my_int, MyInt)
    assert dc.my_int == 123
    assert dc.plain_int == 456

    dump = dc.model_dump()
    assert dump == {"my_int": 123, "plain_int": 456}

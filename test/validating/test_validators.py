"""
Test low-level validation via `Validator` instances.
"""

from typing import Any

from pytest import raises

from typecraft.converting.converter import MatchSpec
from typecraft.inspecting.annotations import ANY, Annotation
from typecraft.validating import (
    BaseTypedGenericValidator,
    TypedValidator,
    TypedValidatorRegistry,
    ValidationEngine,
    ValidationFrame,
    ValidationParams,
)


def test_match_any():
    """
    Test conversion match to/from Any.
    """

    # can convert anything to str
    validator = TypedValidator(Any, str)

    assert validator.check_match(Annotation(int), Annotation(str))
    assert validator.check_match(ANY, Annotation(str))
    assert not validator.check_match(ANY, Annotation(int))

    # can convert str to anything
    validator = TypedValidator(str, Any)
    assert validator.check_match(Annotation(str), ANY)
    assert validator.check_match(Annotation(str), Annotation(int))
    assert validator.check_match(ANY, Annotation(str))


def test_match_assignable():
    """
    Test converter with and without assignable_to_target=True.
    """

    # convert to int, but not bool
    validator = TypedValidator(str, int)
    assert validator.check_match(Annotation(str), Annotation(int))
    assert not validator.check_match(Annotation(str), Annotation(bool))

    # convert to bool, but not int
    validator = TypedValidator(
        str, bool, match_spec=MatchSpec(assignable_to_target=False)
    )
    assert validator.check_match(Annotation(str), Annotation(bool))
    assert not validator.check_match(Annotation(str), Annotation(int))

    # convert to int, or bool since it's a subtype of int
    validator = TypedValidator(
        str,
        int,
        func=lambda obj, frame: frame.target_annotation.concrete_type(obj),
        match_spec=MatchSpec(assignable_from_target=True),
    )
    assert validator.check_match(Annotation(str), Annotation(int))
    assert validator.check_match(Annotation(str), Annotation(bool))


def test_match_custom():
    """
    Test conversion match to/from custom subclasses.
    """

    class CustomInt(int):
        pass

    class CustomStr(str):
        pass

    # can convert to str, but not custom str
    validator = TypedValidator(int, str)
    assert validator.check_match(Annotation(int), Annotation(str))
    assert validator.check_match(Annotation(CustomInt), Annotation(str))
    assert not validator.check_match(Annotation(int), Annotation(CustomStr))
    assert not validator.check_match(Annotation(CustomInt), Annotation(CustomStr))

    # can convert to custom str, but not str
    validator = TypedValidator(
        int, CustomStr, match_spec=MatchSpec(assignable_to_target=False)
    )
    assert validator.check_match(Annotation(int), Annotation(CustomStr))
    assert not validator.check_match(Annotation(int), Annotation(str))

    # can convert from custom int, but not int
    validator = TypedValidator(CustomInt, str)
    assert validator.check_match(Annotation(CustomInt), Annotation(str))
    assert not validator.check_match(Annotation(int), Annotation(str))


def test_match_union_target():
    """
    Test conversion with converter producing a union.
    """

    with raises(
        TypeError,
        match="Cannot use direct object construction when target annotation is a union",
    ):
        _ = TypedValidator(str, int | float)

    # convert based on format of input
    def convert_to_numeric(obj: str) -> int | float:
        return int(obj) if obj.isnumeric() else float(obj)

    validator = TypedValidator.from_func(convert_to_numeric)
    assert validator.check_match(Annotation(str), Annotation(int | float))
    assert validator.check_match(Annotation(str), Annotation(int | float | str))
    assert not validator.check_match(Annotation(str), Annotation(int))
    assert not validator.check_match(Annotation(str), Annotation(float))

    result = validator.convert("1", _create_frame(str, int | float))
    assert isinstance(result, int)
    assert result == 1

    result = validator.convert("1.5", _create_frame(str, int | float))
    assert isinstance(result, float)
    assert result == 1.5

    # convert based on requested type
    def convert_to_numeric_2(obj: str, frame: ValidationFrame) -> int | float:
        if frame.target_annotation.raw is int:
            return int(obj)
        else:
            assert frame.target_annotation.raw is float
            return float(obj)

    validator = TypedValidator.from_func(
        convert_to_numeric_2, match_spec=MatchSpec(assignable_from_target=True)
    )
    assert validator.check_match(Annotation(str), Annotation(int))
    assert validator.check_match(Annotation(str), Annotation(float))
    assert validator.check_match(Annotation(str), Annotation(int | float))


def test_any():
    """
    Test conversion to Any.
    """

    def func1(obj: Any) -> Any:
        assert isinstance(obj, int)
        return -obj

    def func2(obj: Any, frame: ValidationFrame) -> Any:
        assert isinstance(obj, int)
        assert frame.params.strict
        assert frame.target_annotation.concrete_type is object
        return -2 * obj

    obj = 1

    # test both function types
    validator1 = TypedValidator(Any, Any, func=func1)
    validator2 = TypedValidator(Any, Any, func=func2)

    assert validator1.can_convert(obj, ANY, ANY)
    conv_obj = validator1.convert(obj, _create_frame(Any, Any))
    assert conv_obj == -1

    assert validator2.can_convert(obj, ANY, ANY)
    conv_obj = validator2.convert(obj, _create_frame(Any, Any))
    assert conv_obj == -2


def test_generic():
    """
    Test conversion with generic types.
    """

    # convert list of int to list of str
    def func(obj: list[int]) -> list[str]:
        return [str(o) for o in obj]

    # only convert positive int
    def predicate_func(obj: list[int]) -> bool:
        assert isinstance(obj, list)
        assert all(isinstance(o, int) for o in obj)
        return all(o > 0 for o in obj)

    validator = TypedValidator(
        list[int], list[str], func=func, predicate_func=predicate_func
    )
    obj = [123]

    assert validator.check_match(Annotation(list[int]), Annotation(list[str]))
    assert validator.check_match(Annotation(list[Any]), Annotation(list[str]))
    assert not validator.check_match(Annotation(list[Any]), Annotation(list[int]))
    assert not validator.check_match(Annotation(list[float]), Annotation(list[str]))

    assert validator._check_convert(obj, Annotation(list[int]), Annotation(list[str]))
    assert not validator._check_convert(
        [-123], Annotation(list[int]), Annotation(list[str])
    )
    assert not validator._check_convert(
        ["123"], Annotation(list[int]), Annotation(list[str])
    )

    conv_obj = validator.convert(obj, _create_frame(list[int], list[str]))
    assert conv_obj == ["123"]

    conv_obj = validator.convert(obj, _create_frame(list[int], list[Any]))
    assert conv_obj == ["123"]


def test_subclass():
    """
    Test subclass of BaseGenericValidator.
    """

    class MyValidator(BaseTypedGenericValidator[str, int]):

        def can_convert(
            self, obj: str, source_annotation: Annotation, target_annotation: Annotation
        ) -> bool:
            _ = source_annotation, target_annotation
            return obj.isnumeric()

        def convert(self, obj: str, frame: ValidationFrame) -> int:
            _ = frame
            return int(obj)

    validator = MyValidator()
    obj = "123"

    assert validator.check_match(Annotation(str), Annotation(int))
    assert validator.can_convert(obj, Annotation(str), Annotation(int))
    assert not validator.can_convert("abc", Annotation(str), Annotation(int))

    assert validator._check_convert(obj, Annotation(str), Annotation(int))

    conv_obj = validator.convert(obj, _create_frame(str, int))
    assert conv_obj == 123


def test_registry():
    """
    Test converter registry.
    """

    def str_to_int(s: str) -> int:
        """
        Convert string to integer, not encompassing bool.
        """
        return int(s)

    def str_to_int_subtype(s: str, frame: ValidationFrame) -> int:
        """
        Convert string to integer, also encompassing bool.
        """
        return frame.target_annotation.concrete_type(s)

    # register converters (will be checked in reverse order)
    registry = TypedValidatorRegistry()
    registry.register(
        TypedValidator.from_func(
            str_to_int_subtype, match_spec=MatchSpec(assignable_from_target=True)
        )
    )
    registry.register(TypedValidator.from_func(str_to_int))

    # use the registry
    obj = "42"

    validator = registry.find(obj, Annotation(str), Annotation(int))
    assert validator
    assert validator.match_spec.assignable_from_target is False
    assert validator.convert(obj, _create_frame(str, int)) == 42

    validator = registry.find(obj, Annotation(str), Annotation(bool))
    assert validator
    assert validator.match_spec.assignable_from_target is True
    assert validator.convert(obj, _create_frame(str, bool)) is True


def _create_frame(
    source_annotation: Any,
    target_annotation: Any,
    params: ValidationParams | None = None,
) -> ValidationFrame:
    return ValidationEngine().create_frame(
        source_annotation=Annotation(source_annotation),
        target_annotation=Annotation(target_annotation),
        params=params or ValidationParams(strict=True),
        context=None,
    )

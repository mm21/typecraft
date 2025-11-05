"""
Test low-level validation via `Validator` instances.
"""

from typing import Any

from typecraft.inspecting.annotations import ANY, Annotation
from typecraft.validating import (
    ValidationEngine,
    ValidationFrame,
    ValidationParams,
    Validator,
    ValidatorRegistry,
)


def test_match_any():
    """
    Test conversion match to/from Any.
    """

    validator = Validator(Any, str)

    # can convert anything to str
    assert validator.check_match(Annotation(int), Annotation(str))
    assert validator.check_match(Annotation(int), ANY)
    assert validator.check_match(ANY, Annotation(str))
    assert validator.check_match(ANY, ANY)
    assert not validator.check_match(ANY, Annotation(int))


def test_match_subtype():
    """
    Test converter with match_subtype=True.
    """

    validator = Validator(str, int)

    # cannot convert to bool, strictly int
    assert validator.check_match(Annotation(str), Annotation(int))
    assert not validator.check_match(Annotation(str), Annotation(bool))

    validator = Validator(str, int, match_target_subtype=True)

    # can convert to bool since it's a subclass of int
    assert validator.check_match(Annotation(str), Annotation(int))
    assert validator.check_match(Annotation(str), Annotation(bool))

    validator = Validator(int, Any, match_target_subtype=True)

    # can convert from int to anything
    # - not very practical since int is already a subtype of Any
    assert validator.check_match(Annotation(int), ANY)
    assert validator.check_match(Annotation(int), Annotation(str))
    assert validator.check_match(ANY, Annotation(str))


def test_match_custom():
    """
    Test conversion match to/from custom subclasses.
    """

    class CustomInt(int):
        pass

    class CustomStr(str):
        pass

    validator = Validator(int, str)

    # can convert to str, but not custom str
    assert validator.check_match(Annotation(int), Annotation(str))
    assert validator.check_match(Annotation(CustomInt), Annotation(str))
    assert not validator.check_match(Annotation(int), Annotation(CustomStr))
    assert not validator.check_match(Annotation(CustomInt), Annotation(CustomStr))

    validator = Validator(int, CustomStr)

    # can convert to str or custom str
    assert validator.check_match(Annotation(int), Annotation(str))
    assert validator.check_match(Annotation(int), Annotation(CustomStr))

    validator = Validator(CustomInt, str)

    # can convert from custom int, but not int
    assert validator.check_match(Annotation(CustomInt), Annotation(str))
    assert not validator.check_match(Annotation(int), Annotation(str))


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
    converter1 = Validator(Any, Any, func=func1)
    converter2 = Validator(Any, Any, func=func2)

    assert converter1.can_convert(obj, ANY, ANY)
    conv_obj = converter1.convert(obj, _create_frame(Any, Any))
    assert conv_obj == -1

    assert converter2.can_convert(obj, ANY, ANY)
    conv_obj = converter2.convert(obj, _create_frame(Any, Any))
    assert conv_obj == -2


def test_generic():
    """
    Test conversion with generic types.
    """

    def func(obj: list[int]) -> list[str]:
        return [str(o) for o in obj]

    validator = Validator(list[int], list[str], func=func)
    obj = [123]

    assert validator.check_match(Annotation(list[int]), Annotation(list[str]))
    assert validator.check_match(Annotation(list[int]), Annotation(list[Any]))
    assert validator.check_match(Annotation(list[Any]), Annotation(list[str]))
    assert not validator.check_match(Annotation(list[Any]), Annotation(list[int]))
    assert not validator.check_match(Annotation(list[float]), Annotation(list[str]))

    conv_obj = validator.convert(obj, _create_frame(list[int], list[str]))
    assert conv_obj == ["123"]

    conv_obj = validator.convert(obj, _create_frame(list[int], list[Any]))


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

    # register converters
    registry = ValidatorRegistry()
    registry.register(str_to_int)
    registry.register(str_to_int_subtype, match_target_subtype=True)

    # use the registry
    obj = "42"

    validator = registry.find(obj, Annotation(str), Annotation(int))
    assert validator
    assert validator.match_target_subtype is False
    assert validator.convert(obj, _create_frame(str, int)) == 42

    validator = registry.find(obj, Annotation(str), Annotation(bool))
    assert validator
    assert validator.match_target_subtype is True
    assert validator.convert(obj, _create_frame(str, bool)) is True


def _create_frame(
    source_annotation: Any,
    target_annotation: Any,
    params: ValidationParams | None = None,
) -> ValidationFrame:
    engine = ValidationEngine()
    return ValidationFrame(
        source_annotation=Annotation(source_annotation),
        target_annotation=Annotation(target_annotation),
        context=None,
        params=params or ValidationParams(strict=True),
        engine=engine,
    )

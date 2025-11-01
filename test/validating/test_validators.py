"""
Test low-level validation via `Validator` instances.
"""

from typing import Any

from typecraft.inspecting.annotations import ANY, Annotation
from typecraft.validating import (
    ValidationEngine,
    ValidationFrame,
    ValidationHandle,
    ValidationParams,
    Validator,
    ValidatorRegistry,
)


def test_any():
    """
    Test conversion to Any.
    """

    def func1(obj: Any) -> Any:
        assert isinstance(obj, int)
        return -obj

    def func2(obj: Any, handle: ValidationHandle) -> Any:
        assert isinstance(obj, int)
        assert handle.params.strict
        assert handle.target_annotation.concrete_type is object
        return -2 * obj

    obj = 1

    # test both function types
    converter1 = Validator(Any, Any, func=func1)
    converter2 = Validator(Any, Any, func=func2)

    assert converter1.can_convert(obj, ANY, ANY)
    conv_obj = converter1.convert(obj, ANY, ANY, _create_handle(Any))
    assert conv_obj == -1

    assert converter2.can_convert(obj, ANY, ANY)
    conv_obj = converter2.convert(obj, ANY, ANY, _create_handle(Any))
    assert conv_obj == -2


def test_generic():
    """
    Test conversion with generic types.
    """

    def func(obj: Any) -> list[str]:
        return [str(o) for o in obj]

    converter = Validator(list[int], list[str], func=func)
    obj = [123]

    assert converter.can_convert(obj, Annotation(list[int]), Annotation(list[str]))
    assert converter.can_convert(obj, Annotation(list[int]), Annotation(list[Any]))
    assert not converter.can_convert(
        obj, Annotation(list[float]), Annotation(list[str])
    )
    assert not converter.can_convert(obj, Annotation(list[Any]), Annotation(list[str]))

    conv_obj = converter.convert(
        obj, Annotation(list[int]), Annotation(list[str]), _create_handle(list[str])
    )
    assert conv_obj == ["123"]


def test_match_subtype():
    """
    Test converter with match_subtype=True.
    """

    converter = Validator(str, int)
    converter_match_subtype = Validator(str, int, match_target_subtype=True)
    obj = "123"

    # non-match_subtype converter cannot convert to bool, strictly int
    assert converter.can_convert(obj, Annotation(str), Annotation(int))
    assert not converter.can_convert(obj, Annotation(str), Annotation(bool))

    # match_subtype converter can convert to bool since it's a subclass of int
    assert converter_match_subtype.can_convert(obj, Annotation(str), Annotation(int))
    assert converter_match_subtype.can_convert(obj, Annotation(str), Annotation(bool))


def test_registry():
    """
    Test converter registry.
    """

    def str_to_int_inv(s: str) -> int:
        """
        Convert string to integer, not encompassing bool.
        """
        return int(s)

    def str_to_int(s: str, handle: ValidationHandle) -> int:
        """
        Convert string to integer, also encompassing bool.
        """
        return handle.target_annotation.concrete_type(s)

    # register converters
    registry = ValidatorRegistry()
    registry.register(str_to_int_inv, match_target_subtype=True)
    registry.register(str_to_int)

    # use the registry
    obj = "42"

    validator = registry.find(obj, Annotation(str), Annotation(int))
    assert validator
    assert validator.match_target_subtype is False
    assert (
        validator.convert(obj, Annotation(str), Annotation(int), _create_handle(int))
        == 42
    )

    validator = registry.find(obj, Annotation(str), Annotation(bool))
    assert validator
    assert validator.match_target_subtype is True
    assert (
        validator.convert(obj, Annotation(str), Annotation(bool), _create_handle(bool))
        is True
    )


def _create_handle(
    target_annotation: Any, params: ValidationParams | None = None
) -> ValidationHandle:
    engine = ValidationEngine()
    frame = ValidationFrame(
        source_annotation=ANY,
        target_annotation=Annotation(target_annotation),
        context=None,
        params=params or ValidationParams(strict=True),
        engine=engine,
    )
    return ValidationHandle(frame)

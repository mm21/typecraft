"""
Test low-level validation via `TypedValidator` instances.
"""

from typing import Any

from typecraft.inspecting.annotations import Annotation
from typecraft.validating import (
    TypedValidator,
    ValidationEngine,
    ValidationFrame,
    ValidationHandle,
    ValidationParams,
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
        assert handle.target_annotation.concrete_type is object
        assert not handle.params.lenient
        return -2 * obj

    obj = 1

    # test both function types
    converter1 = TypedValidator(Any, Any, func=func1)
    converter2 = TypedValidator(Any, Any, func=func2)

    assert converter1.can_convert(obj, Any)
    conv_obj = converter1.validate(obj, _create_handle(Any))
    assert conv_obj == -1

    assert converter2.can_convert(obj, Annotation(Any))
    conv_obj = converter2.validate(obj, _create_handle(Any))
    assert conv_obj == -2


def test_generic():
    """
    Test conversion with generic types.
    """

    def func(obj: Any) -> list[str]:
        return [str(o) for o in obj]

    converter = TypedValidator(list[int], list[str], func=func)
    obj = [123]

    assert converter.can_convert(obj, list[str])
    assert not converter.can_convert(obj, list[float])
    assert not converter.can_convert(obj, list[Any])
    assert not converter.can_convert(obj, list)

    conv_obj = converter.validate(obj, _create_handle(list[str]))
    assert conv_obj == ["123"]


def test_invariant():
    """
    Test converter with variance="invariant".
    """

    converter_contra = TypedValidator(str, int)
    converter_inv = TypedValidator(str, int, variance="invariant")
    obj = "123"

    # contravariant converter can convert to bool since it's a subclass of int
    assert converter_contra.can_convert(obj, int)
    assert converter_contra.can_convert(obj, bool)

    # invariant convert cannot convert to bool, strictly int
    assert converter_inv.can_convert(obj, int)
    assert not converter_inv.can_convert(obj, bool)


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
    registry.register(str_to_int_inv, variance="invariant")
    registry.register(str_to_int)

    # use the registry
    obj = "42"

    converter = registry.find(obj, Annotation(int))
    assert converter
    assert converter.variance == "invariant"
    assert converter.validate(obj, _create_handle(int)) == 42

    converter = registry.find(obj, Annotation(bool))
    assert converter
    assert converter.variance == "contravariant"
    assert converter.validate(obj, _create_handle(bool)) is True


def _create_handle(
    target_annotation: Any, params: ValidationParams | None = None
) -> ValidationHandle:
    engine = ValidationEngine()
    frame = ValidationFrame._new(
        Annotation(target_annotation),
        params or ValidationParams(lenient=False),
        None,
        engine,
    )
    return ValidationHandle(frame)

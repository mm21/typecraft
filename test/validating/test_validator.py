"""
Test low-level validation via `TypedValidator` instances.
"""

from typing import Any

from modelingkit.inspecting.annotations import Annotation
from modelingkit.validating import (
    TypedValidator,
    TypedValidatorRegistry,
    ValidationContext,
)


def test_any():
    """
    Test conversion to Any.
    """

    def func1(obj: Any) -> Any:
        assert isinstance(obj, int)
        return -obj

    def func2(obj: Any, annotation: Annotation, context: ValidationContext) -> Any:
        assert isinstance(obj, int)
        assert annotation.concrete_type is object
        assert not context.lenient
        return -2 * obj

    obj = 1

    # test both function types
    converter1 = TypedValidator(Any, Any, func=func1)
    converter2 = TypedValidator(Any, Any, func=func2)

    assert converter1.can_validate(obj, Annotation(Any))
    conv_obj = converter1.validate(obj, Annotation(Any), ValidationContext())
    assert conv_obj == -1

    assert converter2.can_validate(obj, Annotation(Any))
    conv_obj = converter2.validate(obj, Annotation(Any), ValidationContext())
    assert conv_obj == -2


def test_generic():
    """
    Test conversion with generic types.
    """

    def func(obj: Any) -> list[str]:
        return [str(o) for o in obj]

    converter = TypedValidator(list[int], list[str], func=func)
    obj = [123]

    assert converter.can_validate(obj, list[str])
    assert not converter.can_validate(obj, list[float])
    assert not converter.can_validate(obj, list[Any])
    assert not converter.can_validate(obj, list)

    conv_obj = converter.validate(obj, Annotation(list[str]), ValidationContext())
    assert conv_obj == ["123"]


def test_invariant():
    """
    Test converter with variance="invariant".
    """

    converter_contra = TypedValidator(str, int)
    converter_inv = TypedValidator(str, int, variance="invariant")
    obj = "123"

    # contravariant converter can convert to bool since it's a subclass of int
    assert converter_contra.can_validate(obj, int)
    assert converter_contra.can_validate(obj, bool)

    # invariant convert cannot convert to bool, strictly int
    assert converter_inv.can_validate(obj, int)
    assert not converter_inv.can_validate(obj, bool)


def test_registry():
    """
    Test converter registry.
    """

    def str_to_int_inv(s: str) -> int:
        """
        Convert string to integer, not encompassing bool.
        """
        return int(s)

    def str_to_int(
        s: str,
        annotation: Annotation,
        context: ValidationContext,
    ) -> int:
        """
        Convert string to integer, also encompassing bool.
        """
        return annotation.concrete_type(s)

    # register converters
    registry = TypedValidatorRegistry()
    registry.register(str_to_int_inv, variance="invariant")
    registry.register(str_to_int)

    # use the registry
    obj = "42"

    converter = registry.find(obj, Annotation(int))
    assert converter
    assert converter.variance == "invariant"
    assert converter.validate(obj, Annotation(int), ValidationContext()) == 42

    converter = registry.find(obj, Annotation(bool))
    assert converter
    assert converter.variance == "contravariant"
    assert converter.validate(obj, Annotation(bool), ValidationContext()) is True

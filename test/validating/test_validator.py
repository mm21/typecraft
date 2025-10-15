"""
Test low-level validation via `TypedValidator` instances.
"""

from typing import Any

from modelingkit.inspecting import Annotation
from modelingkit.validating import (
    TypedValidator,
    TypedValidatorRegistry,
    ValidationContext,
)


def test_any():
    """
    Test conversion to Any.
    """

    def func1(obj: Any):
        assert isinstance(obj, int)
        return -obj

    def func2(obj: Any, annotation: Annotation, context: ValidationContext):
        assert isinstance(obj, int)
        assert annotation.concrete_type is object
        assert not context.lenient
        return -2 * obj

    obj = 1

    # test both function types
    converter1 = TypedValidator(Any, func=func1)
    converter2 = TypedValidator(Any, func=func2)

    assert converter1.can_convert(obj, Annotation(Any))
    conv_obj = converter1.convert(obj, Annotation(Any), ValidationContext())
    assert conv_obj == -1

    assert converter2.can_convert(obj, Annotation(Any))
    conv_obj = converter2.convert(obj, Annotation(Any), ValidationContext())
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

    conv_obj = converter.convert(obj, Annotation(list[str]), ValidationContext())
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

    # create a registry
    registry = TypedValidatorRegistry()

    @registry.register(variance="invariant")
    def str_to_int_inv(s: str) -> int:
        """Convert string to integer, not encompassing bool."""
        return int(s)

    # register converters using decorator
    @registry.register
    def str_to_int(
        s: str,
        annotation: Annotation,
        context: ValidationContext,
    ) -> int:
        """Convert string to integer, also encompassing bool."""
        return annotation.concrete_type(s)

    # use the registry
    obj = "42"

    converter = registry.find(obj, Annotation(int))
    assert converter
    assert converter.variance == "invariant"
    assert converter.convert(obj, Annotation(int), ValidationContext()) == 42

    converter = registry.find(obj, Annotation(bool))
    assert converter
    assert converter.variance == "contravariant"
    assert converter.convert(obj, Annotation(bool), ValidationContext()) is True

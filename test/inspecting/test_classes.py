"""
Tests for class inspection utilities.
"""

from typing import Any, TypeVar

from modelingkit.inspecting.classes import extract_type_param


class BaseContainer[T]:
    """
    Base generic container.
    """


class BaseContainer2[T]:
    """
    Other base generic serializer.
    """


class BaseTransformer[InputT, OutputT]:
    """
    Base with two type parameters.
    """


# type parameters
T = TypeVar("T")
U = TypeVar("U")


def test_direct_inheritance():
    """
    Test extracting type param from direct inheritance.
    """

    class IntContainer(BaseContainer[int]):
        pass

    result = extract_type_param(IntContainer, BaseContainer)
    assert result is int


def test_no_type_param():
    """
    Test class that doesn't inherit from base_cls.
    """

    class UnrelatedClass:
        pass

    result = extract_type_param(UnrelatedClass, BaseContainer)
    assert result is None


def test_generic_without_concrete_type():
    """
    Test generic class that hasn't been parameterized yet.
    """

    class GenericContainer(BaseContainer[T]):
        pass

    # should return None since TypeVar is skipped
    result = extract_type_param(GenericContainer, BaseContainer)
    assert result is None


def test_nested_inheritance():
    """
    Test extracting type param from nested inheritance hierarchy.
    """

    class MiddleContainer[T](BaseContainer[T]):
        pass

    class IntMiddleContainer(MiddleContainer[int]):
        pass

    result = extract_type_param(IntMiddleContainer, BaseContainer)
    assert result is int


def test_deeply_nested_inheritance():
    """
    Test extracting type param from deeply nested inheritance.
    """

    class Level1[T](BaseContainer[T]):
        pass

    class Level2[T](Level1[T]):
        pass

    class Level3[T](Level2[T]):
        pass

    class StrLevel3(Level3[str]):
        pass

    result = extract_type_param(StrLevel3, BaseContainer)
    assert result is str


def test_multiple_type_params_without_filter():
    """
    Test class with multiple type params without param_base_cls filter.
    """

    class StringToIntTransformer(BaseTransformer[str, int]):
        pass

    # without param_base_cls, returns the first matching param
    result = extract_type_param(StringToIntTransformer, BaseTransformer)
    assert result is str


def test_multiple_type_params_with_filter():
    """
    Test distinguishing between multiple type params using param_base_cls.
    """

    class Input:
        pass

    class Output:
        pass

    class InputImpl(Input):
        pass

    class OutputImpl(Output):
        pass

    class MyTransformer(BaseTransformer[InputImpl, OutputImpl]):
        pass

    # extract input type
    result = extract_type_param(MyTransformer, BaseTransformer, Input)
    assert result is InputImpl

    # extract output type
    result = extract_type_param(MyTransformer, BaseTransformer, Output)
    assert result is OutputImpl


def test_nested_with_multiple_type_params():
    """
    Test deeply nested inheritance with multiple type params.
    """

    class Input:
        pass

    class Output:
        pass

    class InputImpl(Input):
        pass

    class OutputImpl(Output):
        pass

    class MiddleTransformer[InputT, OutputT](BaseTransformer[InputT, OutputT]):
        pass

    class ConcreteTransformer(MiddleTransformer[InputImpl, OutputImpl]):
        pass

    result = extract_type_param(ConcreteTransformer, BaseTransformer, Input)
    assert result is InputImpl

    result = extract_type_param(ConcreteTransformer, BaseTransformer, Output)
    assert result is OutputImpl


def test_complex_nested_hierarchy():
    """
    Test complex nested hierarchy with type param changes.
    """

    class Wrapper[T]:
        pass

    class IntWrapper(Wrapper[int]):
        pass

    class DoubleWrapped(BaseContainer[IntWrapper]):
        pass

    result = extract_type_param(DoubleWrapped, BaseContainer)
    assert result is IntWrapper


def test_multiple_bases():
    """
    Test class inheriting from multiple bases.
    """

    class MultiContainer(BaseContainer[int], BaseContainer2[str]):
        pass

    result = extract_type_param(MultiContainer, BaseContainer)
    assert result is int

    result = extract_type_param(MultiContainer, BaseContainer2)
    assert result is str


def test_diamond_inheritance():
    """
    Test diamond inheritance pattern.
    """

    class Left[T](BaseContainer[T]):
        pass

    class Right[T](BaseContainer[T]):
        pass

    class Diamond(Left[int], Right[int]):
        pass

    result = extract_type_param(Diamond, BaseContainer)
    assert result is int


def test_concrete_type_in_middle():
    """
    Test inheritance where concrete type appears in middle of hierarchy.
    """

    class MiddleContainer(BaseContainer[int]):
        pass

    class FinalContainer(MiddleContainer):
        pass

    result = extract_type_param(FinalContainer, BaseContainer)
    assert result is int


def test_repairing_generic():
    """
    Test re-parameterizing a generic in inheritance.
    """

    class MiddleContainer[T](BaseContainer[T]):
        pass

    class StrMiddleContainer(MiddleContainer[str]):
        pass

    class FinalContainer(StrMiddleContainer):
        pass

    result = extract_type_param(FinalContainer, BaseContainer)
    assert result is str


def test_mixed_concrete_and_generic():
    """
    Test mixing concrete types and generics in hierarchy.
    """

    class MiddleContainer[T](BaseContainer[int]):
        pass

    class FinalContainer(MiddleContainer[str]):
        pass

    # should find int since that's what's passed to BaseContainer
    result = extract_type_param(FinalContainer, BaseContainer)
    assert result is int


def test_param_base_cls_not_matching():
    """
    Test param_base_cls that doesn't match any type param.
    """

    class Input:
        pass

    class Output:
        pass

    class Unrelated:
        pass

    class MyTransformer(BaseTransformer[Input, Output]):
        pass

    result = extract_type_param(MyTransformer, BaseTransformer, Unrelated)
    assert result is None


def test_any_type_param():
    """
    Test extracting Any as type parameter.
    """

    class AnyContainer(BaseContainer[Any]):
        pass

    result = extract_type_param(AnyContainer, BaseContainer)
    assert result is Any


def test_nested_generic_type_param():
    """
    Test extracting nested generic as type parameter.
    """

    class ListContainer(BaseContainer[list[int]]):
        pass

    result = extract_type_param(ListContainer, BaseContainer)
    assert result == list[int]


def test_union_type_param():
    """
    Test extracting union type as type parameter.
    """

    class UnionContainer(BaseContainer[int | str]):
        pass

    result = extract_type_param(UnionContainer, BaseContainer)
    assert result == (int | str)


def test_multiple_inheritance_with_same_base():
    """
    Test multiple inheritance where same base appears multiple times.
    """

    class Container1(BaseContainer[int]):
        pass

    class Container2(BaseContainer[bool]):
        pass

    # the first one found should be returned
    class MultiInherit(Container1, Container2):
        pass

    result = extract_type_param(MultiInherit, BaseContainer)

    # should find int first through Container1
    assert result is int


def test_overload_return_types():
    """
    Test that overloads work correctly with different return types.
    """

    class Input:
        pass

    class InputImpl(Input):
        pass

    class MyContainer(BaseContainer[InputImpl]):
        pass

    # without param_base_cls
    result1 = extract_type_param(MyContainer, BaseContainer)
    assert result1 is InputImpl

    # with param_base_cls
    result2 = extract_type_param(MyContainer, BaseContainer, Input)
    assert result2 is InputImpl

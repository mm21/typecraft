"""
Tests for class inspection utilities.
"""

from typing import Any, TypeVar

from pytest import raises

from typecraft.inspecting.generics import extract_arg, extract_arg_map, extract_args


class BaseContainer[T]:
    """
    Base generic container.
    """


class BaseContainer2[T]:
    """
    Other base generic container.
    """


class IntContainer(BaseContainer[int]):
    """
    Container of int.
    """


class MiddleContainer[T](BaseContainer[T]):
    """
    Intermediate between concrete and base container.
    """


class IntMiddleContainer(MiddleContainer[int]):
    """
    Container of int with middle container.
    """


class BaseTransformer[InputT, OutputT]:
    """
    Base with two type parameters.
    """


class StringToIntTransformer(BaseTransformer[str, int]):
    """
    Concrete class with str and int parameters.
    """


class Input:
    pass


class Output:
    pass


class InputImpl(Input):
    pass


class OutputImpl(Output):
    pass


class UnrelatedClass:
    """
    Class unrelated to any others.
    """


# type parameters
T = TypeVar("T")
U = TypeVar("U")


def test_all_args():
    """
    Test extracting all args.
    """
    result = extract_arg_map(IntContainer, BaseContainer)
    assert result == {"T": int}

    result = extract_args(IntContainer, BaseContainer)
    assert result == (int,)

    result = extract_arg_map(IntMiddleContainer, BaseContainer)
    assert result == {"T": int}

    result = extract_args(IntMiddleContainer, BaseContainer)
    assert result == (int,)


def test_extract_args_with_typevar():
    """
    Test that extract_arg_map includes unresolved TypeVars.
    """

    class GenericTransformer(BaseTransformer[T, int]):
        pass

    result = extract_arg_map(GenericTransformer, BaseTransformer)

    # should include the unresolved TypeVar
    assert list(result.keys()) == ["InputT", "OutputT"]
    assert isinstance(result["InputT"], TypeVar)
    assert result["InputT"] is T
    assert result["OutputT"] is int

    result = extract_args(GenericTransformer, BaseTransformer)
    assert result == (T, int)


def test_direct_inheritance():
    """
    Test extracting type param from direct inheritance.
    """
    result = extract_arg(IntContainer, BaseContainer, "T")
    assert result is int


def test_extract_args_empty_params():
    """
    Test extracting args from a base class with no type parameters.
    """

    class NonGenericBase:
        pass

    class Derived(NonGenericBase):
        pass

    with raises(TypeError, match="not found in .*?'s inheritance hierarchy"):
        extract_arg_map(Derived, BaseContainer)


def test_no_type_param():
    """
    Test class that doesn't inherit from base_cls.
    """
    with raises(TypeError, match="not found in .*?'s inheritance hierarchy"):
        _ = extract_arg(UnrelatedClass, BaseContainer, "T")


def test_generic_without_concrete_type():
    """
    Test generic class that hasn't been parameterized yet.
    """

    class GenericContainer(BaseContainer[T]):
        pass

    with raises(ValueError, match="Type parameter with name .*? is unresolved"):
        _ = extract_arg(GenericContainer, BaseContainer, "T")


def test_nested_inheritance():
    """
    Test extracting type param from nested inheritance hierarchy.
    """
    result = extract_arg(IntMiddleContainer, BaseContainer, "T")
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

    result = extract_arg(StrLevel3, BaseContainer, "T")
    assert result is str


def test_extract_by_index():
    """
    Test extracting type params by index.
    """
    result = extract_arg(StringToIntTransformer, BaseTransformer, 0)
    assert result is str

    result = extract_arg(StringToIntTransformer, BaseTransformer, 1)
    assert result is int


def test_extract_by_index_with_param_cls():
    """
    Test extracting type params by index with param_cls filter.
    """

    class MyTransformer(BaseTransformer[InputImpl, OutputImpl]):
        pass

    # extract input type by index
    result = extract_arg(MyTransformer, BaseTransformer, 0, Input)
    assert result is InputImpl

    # extract output type by index
    result = extract_arg(MyTransformer, BaseTransformer, 1, Output)
    assert result is OutputImpl


def test_index_with_partially_resolved():
    """
    Test extracting by index when some params are resolved and some aren't.
    """

    class PartialTransformer[T](BaseTransformer[T, int]):
        pass

    # index 1 should work (resolved to int)
    result = extract_arg(PartialTransformer, BaseTransformer, 1)
    assert result is int

    # index 0 should raise (unresolved TypeVar)
    with raises(ValueError, match="Type parameter with index 0 is unresolved"):
        extract_arg(PartialTransformer, BaseTransformer, 0)


def test_extract_invalid():
    """
    Test extracting with non-existent parameter name.
    """
    with raises(KeyError, match="Type parameter 'NonExistent' not found"):
        extract_arg(StringToIntTransformer, BaseTransformer, "NonExistent")

    with raises(IndexError, match="Type parameter index 2 out of range"):
        extract_arg(StringToIntTransformer, BaseTransformer, 2)


def test_extract_unresolved_typevar():
    """
    Test extracting unresolved TypeVar by index raises ValueError.
    """

    class GenericTransformer[T, U](BaseTransformer[T, U]):
        pass

    with raises(ValueError, match="Type parameter with index 0 is unresolved"):
        extract_arg(GenericTransformer, BaseTransformer, 0)


def test_multiple_type_params_without_filter():
    """
    Test class with multiple type params without param_cls filter.
    """
    result = extract_arg(StringToIntTransformer, BaseTransformer, "InputT")
    assert result is str


def test_multiple_type_params_with_filter():
    """
    Test distinguishing between multiple type params using param_cls.
    """

    class MyTransformer(BaseTransformer[InputImpl, OutputImpl]):
        pass

    # extract input type
    result = extract_arg(MyTransformer, BaseTransformer, "InputT", Input)
    assert result is InputImpl

    # extract output type
    result = extract_arg(MyTransformer, BaseTransformer, "OutputT", Output)
    assert result is OutputImpl


def test_nested_with_multiple_type_params():
    """
    Test deeply nested inheritance with multiple type params.
    """

    class MiddleTransformer[InputT, OutputT](BaseTransformer[InputT, OutputT]):
        pass

    class ConcreteTransformer(MiddleTransformer[InputImpl, OutputImpl]):
        pass

    result = extract_arg(ConcreteTransformer, BaseTransformer, "InputT", Input)
    assert result is InputImpl

    result = extract_arg(ConcreteTransformer, BaseTransformer, "OutputT", Output)
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

    result = extract_arg(DoubleWrapped, BaseContainer, "T")
    assert result is IntWrapper


def test_multiple_bases():
    """
    Test class inheriting from multiple bases.
    """

    class MultiContainer(BaseContainer[int], BaseContainer2[str]):
        pass

    result = extract_arg(MultiContainer, BaseContainer, "T")
    assert result is int

    result = extract_arg(MultiContainer, BaseContainer2, "T")
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

    result = extract_arg(Diamond, BaseContainer, "T")
    assert result is int


def test_concrete_type_in_middle():
    """
    Test inheritance where concrete type appears in middle of hierarchy.
    """

    class MiddleContainer(BaseContainer[int]):
        pass

    class FinalContainer(MiddleContainer):
        pass

    result = extract_arg(FinalContainer, BaseContainer, "T")
    assert result is int


def test_mixed_concrete_and_generic():
    """
    Test mixing concrete types and generics in hierarchy.
    """

    class MiddleContainer[T](BaseContainer[int]):
        pass

    class FinalContainer(MiddleContainer[str]):
        pass

    # should find int since that's what's passed to BaseContainer
    result = extract_arg(FinalContainer, BaseContainer, "T")
    assert result is int


def test_param_cls_not_matching():
    """
    Test param_cls that doesn't match any type param.
    """

    class MyTransformer(BaseTransformer[Input, Output]):
        pass

    # should raise TypeError when param_cls doesn't match
    with raises(TypeError, match="does not match required base class"):
        extract_arg(MyTransformer, BaseTransformer, "InputT", UnrelatedClass)


def test_any_type_param():
    """
    Test extracting Any as type parameter.
    """

    class AnyContainer(BaseContainer[Any]):
        pass

    result = extract_arg(AnyContainer, BaseContainer, "T")
    assert result is Any


def test_nested_generic_type_param():
    """
    Test extracting nested generic as type parameter.
    """

    class ListContainer(BaseContainer[list[int]]):
        pass

    result = extract_arg(ListContainer, BaseContainer, "T")
    assert result == list[int]


def test_union_type_param():
    """
    Test extracting union type as type parameter.
    """

    class UnionContainer(BaseContainer[int | str]):
        pass

    result = extract_arg(UnionContainer, BaseContainer, "T")
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

    result = extract_arg(MultiInherit, BaseContainer, "T")

    # should find int first through Container1
    assert result is int


def test_overload_return_types():
    """
    Test that overloads work correctly with different return types.
    """

    class MyContainer(BaseContainer[InputImpl]):
        pass

    # without param_cls
    result = extract_arg(MyContainer, BaseContainer, "T")
    assert result is InputImpl

    # with param_cls
    result = extract_arg(MyContainer, BaseContainer, "T", Input)
    assert result is InputImpl


def test_builtins():
    """
    Test extracting args from builtins, which have no typevars.
    """

    class MyList(list[int]):
        pass

    class MyParameterizedList[T](list[T]):
        pass

    class MyTuple(tuple[int, str]):
        pass

    class MyDict(dict[int, str]):
        pass

    class MyParameterizedDict[K, V](dict[K, V]):
        pass

    result = extract_args(MyList, list)
    assert result == (int,)

    result = extract_arg_map(MyList, list)
    assert result == {}

    result = extract_arg(MyList, list, 0)
    assert result is int

    result = extract_args(MyParameterizedList[int], list)
    assert result == (int,)

    result = extract_arg_map(MyParameterizedList, list)
    assert list(result.keys()) == ["T"]

    result = extract_args(MyTuple, tuple)
    assert result == (int, str)

    result = extract_arg_map(MyTuple, tuple)
    assert result == {}

    result = extract_args(MyDict, dict)
    assert result == (int, str)

    result = extract_arg_map(MyDict, dict)
    assert result == {}

    result = extract_args(MyParameterizedDict[int, str], dict)
    assert result == (int, str)

    result = extract_arg_map(MyParameterizedDict[int, str], dict)
    assert list(result.keys()) == ["K", "V"]


def test_from_self():
    """
    Test extracting args from same base class.
    """

    result = extract_arg_map(BaseContainer, BaseContainer)
    assert len(result) == 1
    assert result["T"].__name__ == "T"

    result = extract_args(list[int], list)
    assert result == (int,)

    result = extract_arg(list[int], list, 0)
    assert result is int

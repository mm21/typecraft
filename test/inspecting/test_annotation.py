"""
Tests for `Annotation` class.
"""

from collections.abc import Callable
from typing import Any, Literal, Sequence, Union

from modelingkit.inspecting import Annotation, is_instance, is_subclass

type ListAlias = list[int]


def test_alias():
    """
    Test normalizing type alias.
    """
    a = Annotation(ListAlias)
    assert a.origin is list
    assert len(a.args) == 1
    assert a.args[0] is int


def test_union():
    """
    Test methods of defining unions.
    """
    a = Annotation(int | str)
    assert a.is_union

    a = Annotation(Union[int, str])
    assert a.is_union


def test_is_subclass():
    """
    Test `is_subclass` / `Annotation.is_subclass()` checks.
    """
    a1 = Annotation(int)
    a2 = Annotation(Any)
    assert a1.is_subclass(a2)
    assert a1.is_subclass(Any)
    assert not a2.is_subclass(a1)

    a1 = Annotation(list[int])
    a2 = Annotation(list[Any])
    assert a1.is_subclass(a2)
    assert not a2.is_subclass(a1)

    # same but with alias
    assert is_subclass(ListAlias, list[Any])
    assert not is_subclass(list[Any], ListAlias)

    a1 = Annotation(list[int])
    a2 = Annotation(list[float])
    assert not a1.is_subclass(a2)
    assert not a2.is_subclass(a1)

    a1 = Annotation(list[list[bool]])
    a2 = Annotation(list[list[int]])
    assert a1.is_subclass(a2)
    assert not a2.is_subclass(a1)

    # list is assumed to be list[Any]
    a1 = Annotation(list[int])
    a2 = Annotation(list)
    assert a1.is_subclass(a2)
    assert not a2.is_subclass(a1)

    a1 = Annotation(list[Any])
    a2 = Annotation(list)
    assert a1.is_subclass(a2)
    assert a2.is_subclass(a1)

    # unions
    a1 = Annotation(int)
    a2 = Annotation(int | str)
    assert a1.is_subclass(a2)
    assert not a2.is_subclass(a1)

    a1 = Annotation(int | str)
    a2 = Annotation(int | str | float)
    assert a1.is_subclass(a2)
    assert not a2.is_subclass(a1)

    a1 = Annotation(list[int | str])
    a2 = Annotation(list)
    assert a1.is_subclass(a2)
    assert not a2.is_subclass(a1)

    # literals
    a1 = Annotation(Literal["a"])
    a2 = Annotation(Literal["a", "b"])
    assert a1.is_subclass(a2)
    assert not a2.is_subclass(a1)

    a2 = Annotation(str)
    assert a1.is_subclass(a2)
    assert not a2.is_subclass(a1)

    a3 = Annotation(Literal["a", "b"] | int)
    a4 = Annotation(int)
    assert a1.is_subclass(a3)
    assert a4.is_subclass(a3)
    assert not a3.is_subclass(a1)
    assert not a3.is_subclass(a4)


def test_is_instance():
    """
    Test `is_instance()` / `Annotation.is_type()` checks.
    """
    # non-generics
    a = Annotation(Any)
    assert a.is_type(1)

    a = Annotation(int)
    assert a.is_type(123)
    assert not a.is_type("123")
    assert not a.is_type([123])

    a = Annotation(list)
    assert a.is_type([1, "2"])

    a = Annotation(set)
    assert a.is_type({1, "2"})

    a = Annotation(tuple)
    assert a.is_type((1, "2"))

    a = Annotation(dict)
    assert a.is_type({"a": 1})

    # parameterized lists
    a = Annotation(list[Any])
    assert a.is_type([1, "2"])
    assert a.is_type([])
    assert not a.is_type(1)

    a = Annotation(list[int])
    assert a.is_type([1, 2])
    assert a.is_type([])
    assert not a.is_type([1, "2"])

    # same but with alias
    assert is_instance([1, 2], ListAlias)
    assert is_instance([], ListAlias)
    assert not is_instance([1, "2"], ListAlias)

    a = Annotation(list[int | str])
    assert a.is_type([1, "2"])
    assert not a.is_type([1, "2", 3.0])

    # parameterized set
    a = Annotation(set[int])
    assert a.is_type({1, 2, 3})
    assert a.is_type(set())
    assert not a.is_type({1, "2"})

    # parameterized fixed-length tuple
    a = Annotation(tuple[int, str])
    assert a.is_type((1, "2"))
    assert not a.is_type((1, 2))

    # parameterized homogeneous tuple
    a = Annotation(tuple[int, ...])
    assert a.is_type((1,))
    assert a.is_type((1, 2))
    assert not a.is_type((1, "2"))

    # parameterized dicts
    a = Annotation(dict[str, int])
    assert a.is_type({"a": 1, "b": 2})
    assert not a.is_type({0: 1})
    assert not a.is_type({"a": "1"})

    a = Annotation(dict[str, Any])
    assert a.is_type({"a": 1, "b": "2"})
    assert not a.is_type({0: 1})

    # unions
    a = Annotation(int | str)
    assert a.is_type(1)
    assert a.is_type("a")
    assert not a.is_type(1.0)

    a = Annotation(Union[int, str])
    assert a.is_type(1)
    assert a.is_type("a")
    assert not a.is_type(1.0)

    # literals
    a = Annotation(Literal["a", "b"])
    assert a.is_type("a")
    assert not a.is_type("c")
    assert not a.is_type(1)


def test_eq():
    """
    Test equality check.
    """
    assert Annotation(int) == Annotation(int)
    assert Annotation(list[Any]) == Annotation(list[Any])
    assert Annotation(list) == Annotation(list[Any])
    assert Annotation(list[str]) != Annotation(list[Any])


def test_callable():
    """
    Test callable annotation handling.
    """
    # basic callable
    a = Annotation(Callable[[int, str], bool])
    assert a.is_callable
    assert a.origin is Callable
    assert a.param_annotations is not None
    assert len(a.param_annotations) == 2
    assert a.param_annotations[0].annotation is int
    assert a.param_annotations[1].annotation is str
    assert a.return_annotation is not None
    assert a.return_annotation.annotation is bool

    # callable with ... params
    a = Annotation(Callable[..., int])
    assert a.is_callable
    assert a.param_annotations is None
    assert a.return_annotation is not None
    assert a.return_annotation.annotation is int

    # callable with no args
    a = Annotation(Callable[[], str])
    assert a.is_callable
    assert a.param_annotations is not None
    assert len(a.param_annotations) == 0
    assert a.return_annotation is not None
    assert a.return_annotation.annotation is str


def test_callable_is_subclass():
    """
    Test is_subclass for callables.

    Callables are contravariant in parameters and covariant in return type.
    """
    # same signature
    a1 = Annotation(Callable[[int], str])
    a2 = Annotation(Callable[[int], str])
    assert a1.is_subclass(a2)
    assert a2.is_subclass(a1)

    # covariant return type (bool is subclass of int)
    a1 = Annotation(Callable[[int], bool])
    a2 = Annotation(Callable[[int], int])
    assert a1.is_subclass(a2)
    assert not a2.is_subclass(a1)

    # contravariant parameters (bool is subclass of int)
    # - Callable[[int], str] accepts any int, including bool
    # so it's a subtype of Callable[[bool], str]
    a1 = Annotation(Callable[[int], str])
    a2 = Annotation(Callable[[bool], str])
    assert a1.is_subclass(a2)
    assert not a2.is_subclass(a1)

    # different parameter count
    a1 = Annotation(Callable[[int], str])
    a2 = Annotation(Callable[[int, int], str])
    assert not a1.is_subclass(a2)
    assert not a2.is_subclass(a1)

    # Callable[..., T] accepts any parameters
    a1 = Annotation(Callable[[int, str], bool])
    a2 = Annotation(Callable[..., bool])
    assert a1.is_subclass(a2)
    assert not a2.is_subclass(a1)

    # return type still matters with ...
    a1 = Annotation(Callable[..., bool])
    a2 = Annotation(Callable[..., int])
    assert a1.is_subclass(a2)  # bool is subclass of int
    assert not a2.is_subclass(a1)

    # Callable with Any
    a1 = Annotation(Callable[[int], Any])
    a2 = Annotation(Callable[[int], str])
    assert a2.is_subclass(a1)  # str is subclass of Any
    assert not a1.is_subclass(a2)

    # multiple parameters with contravariance
    a1 = Annotation(Callable[[int, str], bool])
    a2 = Annotation(Callable[[bool, str], bool])
    assert a1.is_subclass(a2)
    assert not a2.is_subclass(a1)

    # complex nested types
    a1 = Annotation(Callable[[list[int]], str])
    a2 = Annotation(Callable[[list[bool]], str])
    a3 = Annotation(Callable[[tuple[int]], str])
    a4 = Annotation(Callable[[Sequence[int]], str])
    assert a1.is_subclass(a2)  # list[int] accepts list[bool]
    assert not a2.is_subclass(a1)
    assert not a1.is_subclass(a3)
    assert not a1.is_subclass(a4)
    assert a4.is_subclass(a1)


def test_callable_type_is_subclass():
    """
    Test that type annotations (type[int], type[str], etc.) are recognized as callables.

    Note: The annotation `int` represents instances of int (not callable).
    The annotation `type[int]` represents the type itself (callable).
    """
    # type[int] is like Callable[..., int]
    a1 = Annotation(type[int])
    a2 = Annotation(Callable[[Any], int])
    assert a1.is_subclass(a2)

    # type[int] is also a subclass of Callable[..., int]
    a2 = Annotation(Callable[..., int])
    assert a1.is_subclass(a2)

    # type[int] is a subclass of Callable[[str], int] (broader params)
    a2 = Annotation(Callable[[str], int])
    assert a1.is_subclass(a2)

    # type[int] is NOT a subclass of Callable[[Any], bool] (wrong return type)
    a2 = Annotation(Callable[[Any], bool])
    assert not a1.is_subclass(a2)

    # type[int] is NOT a subclass of Callable[[Any], str] (wrong return type)
    a2 = Annotation(Callable[[Any], str])
    assert not a1.is_subclass(a2)

    # type[str] is like Callable[..., str]
    a1 = Annotation(type[str])
    a2 = Annotation(Callable[[Any], str])
    assert a1.is_subclass(a2)

    # type[list] is like Callable[..., list]
    a1 = Annotation(type[list])
    a2 = Annotation(Callable[[Any], list])
    assert a1.is_subclass(a2)

    # more complex: type[int] with union in Callable
    a1 = Annotation(type[int])
    a2 = Annotation(Callable[[int | str], int])
    assert a1.is_subclass(a2)

    # test with multiple parameters
    a1 = Annotation(type[int])
    a2 = Annotation(Callable[[Any, Any], int])
    assert a1.is_subclass(a2)  # type[int] accepts any number of args

    # but Callable[[Any], int] is NOT a subclass of type[int]
    a1 = Annotation(Callable[[Any], int])
    a2 = Annotation(type[int])
    assert not a1.is_subclass(a2)

    # verify that plain `int` is NOT treated as callable
    a1 = Annotation(int)
    a2 = Annotation(Callable[[Any], int])
    assert not a1.is_subclass(a2)  # int instances are not callable


def test_callable_is_instance():
    """
    Test is_type for callables.
    """

    def func1(x: int, y: str) -> bool:
        return True

    def func2(x: int) -> str:
        return "test"

    def func3() -> int:
        return 42

    # check basic callable
    a = Annotation(Callable[[int, str], bool])
    assert a.is_type(func1)
    assert not a.is_type(func2)  # wrong parameter count
    assert not a.is_type(func3)  # wrong parameter count
    assert not a.is_type(123)  # not callable

    # check Callable[..., T]
    a = Annotation(Callable[..., int])
    assert a.is_type(func1)  # any parameters acceptable
    assert a.is_type(func2)
    assert a.is_type(func3)
    assert a.is_type(lambda: 42)
    assert not a.is_type("not callable")

    # test with lambda
    a = Annotation(Callable[[int], str])
    assert a.is_type(lambda x: str(x))
    assert not a.is_type(lambda x, y: str(x))  # wrong param count

    # test with no parameters
    a = Annotation(Callable[[], int])
    assert a.is_type(int)
    assert a.is_type(func3)
    assert a.is_type(lambda: 42)
    assert not a.is_type(func1)

    # test with built-in functions (may not have inspectable signature)
    a = Annotation(Callable[..., Any])
    assert a.is_type(len)
    assert a.is_type(print)

    # test with classes (they're callable too)
    a = Annotation(Callable[..., Any])
    assert a.is_type(int)
    assert a.is_type(str)
    assert a.is_type(list)

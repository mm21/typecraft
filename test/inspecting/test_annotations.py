"""
Tests for `Annotation` class.
"""

from collections.abc import Callable
from typing import Any, Literal, Sequence, Union

from typecraft.inspecting.annotations import Annotation

type ListAlias = list[int]
type RecursiveAlias = list[RecursiveAlias] | int


def test_alias():
    """
    Test normalizing type alias.
    """
    a = Annotation(ListAlias)
    assert a.origin is list
    assert len(a.args) == 1
    assert a.args[0] is int


def test_recursive_alias():
    """
    Test recursive alias.
    """
    a = Annotation(RecursiveAlias)
    assert a.is_union
    assert len(a.arg_annotations) == 2

    arg1, arg2 = a.arg_annotations
    assert arg1.concrete_type is list
    assert arg2.concrete_type is int

    # arg1 should be a list of RecursiveAlias, the same Annotation object
    assert len(arg1.arg_annotations) == 1
    assert arg1.arg_annotations[0] is a


def test_union():
    """
    Test methods of defining unions.
    """
    a = Annotation(int | str)
    assert a.is_union

    a = Annotation(Union[int, str])
    assert a.is_union


def test_is_assignable():
    """
    Test `Annotation.is_assignable()` checks.
    """

    # int is a subtype of itself
    a1 = Annotation(int)
    a2 = Annotation(int)
    assert a1.is_assignable(a2)

    # list[int] is not a subtype of list[float]
    a1 = Annotation(list[int])
    a2 = Annotation(list[float])
    assert not a1.is_assignable(a2)
    assert not a2.is_assignable(a1)

    # nested generics with Any maintain bidirectionality
    a1 = Annotation(list[list[bool]])
    a2 = Annotation(list[list[int]])
    assert a1.is_assignable(a2)
    assert not a2.is_assignable(a1)

    a1 = Annotation(list[list[bool]])
    a2 = Annotation(list[list[Any]])
    assert a1.is_assignable(a2)  # top type
    assert a2.is_assignable(a1)  # bottom type

    a1 = Annotation(list[list[Any]])
    a2 = Annotation(list[Any])
    assert a1.is_assignable(a2)  # both work due to Any
    assert a2.is_assignable(a1)  # bidirectional

    # list is assumed to be list[Any]
    a1 = Annotation(list[int])
    a2 = Annotation(list)
    assert a1.is_assignable(a2)
    assert a2.is_assignable(a1)  # bidirectional now

    a1 = Annotation(list[Any])
    a2 = Annotation(list)
    assert a1.is_assignable(a2)
    assert a2.is_assignable(a1)

    a1 = Annotation(int)
    a2 = Annotation(int | str)
    assert a1.is_assignable(a2)
    assert not a2.is_assignable(a1)

    a1 = Annotation(int | str)
    a2 = Annotation(int | str | float)
    assert a1.is_assignable(a2)
    assert not a2.is_assignable(a1)

    a1 = Annotation(list[int | str])
    a2 = Annotation(list)
    assert a1.is_assignable(a2)
    assert a2.is_assignable(a1)  # bidirectional

    a1 = Annotation(int | str)
    a2 = Annotation(Any)
    assert a1.is_assignable(a2)  # top type
    assert a2.is_assignable(a1)  # bottom type

    # literals with Any
    a1 = Annotation(Literal["a"])
    a2 = Annotation(Literal["a", "b"])
    assert a1.is_assignable(a2)
    assert not a2.is_assignable(a1)

    a2 = Annotation(str)
    assert a1.is_assignable(a2)
    assert not a2.is_assignable(a1)

    a3 = Annotation(Literal["a", "b"] | int)
    a4 = Annotation(int)
    assert a1.is_assignable(a3)
    assert a4.is_assignable(a3)
    assert not a3.is_assignable(a1)
    assert not a3.is_assignable(a4)

    # literals with Any are bidirectional
    a1 = Annotation(Literal["a", "b"])
    a2 = Annotation(Any)
    assert a1.is_assignable(a2)  # top type
    assert a2.is_assignable(a1)  # bottom type


def test_check_instance():
    """
    Test `Annotation.check_instance()` checks.
    """
    # non-generics
    a = Annotation(Any)
    assert a.check_instance(1)

    a = Annotation(int)
    assert a.check_instance(123)
    assert not a.check_instance("123")
    assert not a.check_instance([123])

    a = Annotation(list)
    assert a.check_instance([1, "2"])

    a = Annotation(set)
    assert a.check_instance({1, "2"})

    a = Annotation(tuple)
    assert a.check_instance((1, "2"))

    a = Annotation(dict)
    assert a.check_instance({"a": 1})

    # parameterized lists
    a = Annotation(list[Any])
    assert a.check_instance([1, "2"])
    assert a.check_instance([])
    assert not a.check_instance(1)

    a = Annotation(list[int])
    assert a.check_instance([1, 2])
    assert a.check_instance([])
    assert not a.check_instance([1, "2"])

    # same but with alias
    a = Annotation(ListAlias)
    assert a.check_instance([1, 2])
    assert a.check_instance([])
    assert not a.check_instance([1, "2"])

    a = Annotation(list[int | str])
    assert a.check_instance([1, "2"])
    assert not a.check_instance([1, "2", 3.0])

    # parameterized set
    a = Annotation(set[int])
    assert a.check_instance({1, 2, 3})
    assert a.check_instance(set())
    assert not a.check_instance({1, "2"})

    # parameterized fixed-length tuple
    a = Annotation(tuple[int, str])
    assert a.check_instance((1, "2"))
    assert not a.check_instance((1, 2))

    # parameterized homogeneous tuple
    a = Annotation(tuple[int, ...])
    assert a.check_instance((1,))
    assert a.check_instance((1, 2))
    assert not a.check_instance((1, "2"))

    # parameterized dicts
    a = Annotation(dict[str, int])
    assert a.check_instance({"a": 1, "b": 2})
    assert not a.check_instance({0: 1})
    assert not a.check_instance({"a": "1"})

    a = Annotation(dict[str, Any])
    assert a.check_instance({"a": 1, "b": "2"})
    assert not a.check_instance({0: 1})

    # unions
    a = Annotation(int | str)
    assert a.check_instance(1)
    assert a.check_instance("a")
    assert not a.check_instance(1.0)

    a = Annotation(Union[int, str])
    assert a.check_instance(1)
    assert a.check_instance("a")
    assert not a.check_instance(1.0)

    # literals
    a = Annotation(Literal["a", "b"])
    assert a.check_instance("a")
    assert not a.check_instance("c")
    assert not a.check_instance(1)

    # no recursion
    a = Annotation(list[str])
    assert a.check_instance([1], recurse=False)
    assert not a.check_instance([1])
    a = Annotation(int | str)
    assert a.check_instance(1, recurse=False)
    assert a.check_instance("a", recurse=False)
    assert not a.check_instance(1.0, recurse=False)


def test_generic_subclass():
    """
    Test subclass of generic types.
    """

    class IntList(list[int]):
        pass

    class IntStrDict(dict[int, str]):
        pass

    a = Annotation(IntList)
    assert a.is_assignable(list[int])
    assert a.check_instance(IntList([1]))
    assert not a.check_instance(IntList(["a"]))  # type: ignore
    assert not a.check_instance([1])

    a = Annotation(IntStrDict)
    assert a.is_assignable(dict[int, str])
    assert a.check_instance(IntStrDict({1: "a"}))
    assert not a.check_instance(IntStrDict({1: 1}))  # type: ignore
    assert not a.check_instance({1: "a"})


def test_eq():
    """
    Test equality check.
    """
    assert Annotation(int) == Annotation(int)
    assert Annotation(int) != Annotation(Any)
    assert Annotation(list[Any]) == Annotation(list[Any])
    assert Annotation(list) == Annotation(list[Any])
    assert Annotation(list[int]) != Annotation(list[Any])
    assert Annotation(Literal["a", "b"]) != Annotation(Any)


def test_any_vs_object():
    """
    Test the critical distinction between Any (top AND bottom type) and object
    (concrete top type).

    Any is BOTH the top type and bottom type in Python's gradual typing system:
    - Everything is a subtype of Any (top type behavior)
    - Any is a subtype of everything (bottom type behavior)

    `object` is a concrete class - only actual object subclasses are subtypes of object.
    """
    # Any as TOP type - everything is a subtype of Any
    assert Annotation(int).is_assignable(Any)
    assert Annotation(str).is_assignable(Any)
    assert Annotation(list).is_assignable(Any)
    assert Annotation(list[int]).is_assignable(Any)
    assert Annotation(dict[str, Any]).is_assignable(Any)
    assert Annotation(Callable[[int], str]).is_assignable(Any)

    # Any as BOTTOM type - Any is a subtype of everything
    assert Annotation(Any).is_assignable(int)
    assert Annotation(Any).is_assignable(str)
    assert Annotation(Any).is_assignable(object)
    assert Annotation(Any).is_assignable(list)
    assert Annotation(Any).is_assignable(list[int])
    assert Annotation(Any).is_assignable(Callable[[str], bool])

    # Any is both a subtype of itself (top meets bottom)
    assert Annotation(Any).is_assignable(Any)

    # object is a concrete type
    assert Annotation(int).is_assignable(object)
    assert Annotation(str).is_assignable(object)
    assert Annotation(list).is_assignable(object)
    # Any is also a subtype of object (bottom type property)
    assert Annotation(Any).is_assignable(object)
    # object is a subtype of Any (top type property)
    assert Annotation(object).is_assignable(Any)

    # in generic type parameters, Any maintains its dual nature
    assert Annotation(list[int]).is_assignable(list[Any])  # top type
    assert Annotation(list[Any]).is_assignable(list[int])  # bottom type
    assert Annotation(dict[str, int]).is_assignable(dict[str, Any])  # top type
    assert Annotation(dict[Any, Any]).is_assignable(dict[str, int])  # bottom type

    # list[object] is different from list[Any]
    assert Annotation(list[int]).is_assignable(list[object])  # normal covariance
    assert not Annotation(list[object]).is_assignable(list[int])

    # with callables, Any in parameters and return types:
    # Any in return (bottom type): can return anything
    assert Annotation(Callable[[int], Any]).is_assignable(Callable[[int], str])
    # Any in parameters (bottom type meets contravariance)
    assert Annotation(Callable[[Any], str]).is_assignable(Callable[[int], str])
    assert Annotation(Callable[[int], str]).is_assignable(Callable[[Any], Any])
    assert Annotation(Callable[[Any], Any]).is_assignable(Callable[[int], str])

    # nested generics
    assert Annotation(list[list[int]]).is_assignable(list[list[Any]])
    assert Annotation(list[list[Any]]).is_assignable(list[list[int]])
    assert Annotation(list[list[int]]).is_assignable(list[Any])
    assert Annotation(list[Any]).is_assignable(list[list[int]])

    # unions with Any
    assert Annotation(int | str).is_assignable(Any)
    assert Annotation(Any).is_assignable(int | str)


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
    assert a.param_annotations[0].raw is int
    assert a.param_annotations[1].raw is str
    assert a.return_annotation is not None
    assert a.return_annotation.raw is bool

    # callable with ... params
    a = Annotation(Callable[..., int])
    assert a.is_callable
    assert a.param_annotations is None
    assert a.return_annotation is not None
    assert a.return_annotation.raw is int

    # callable with no args
    a = Annotation(Callable[[], str])
    assert a.is_callable
    assert a.param_annotations is not None
    assert len(a.param_annotations) == 0
    assert a.return_annotation is not None
    assert a.return_annotation.raw is str


def test_callable_is_assignable():
    """
    Test is_assignable for callables.

    Callables are contravariant in parameters and covariant in return type.
    With Any as both top and bottom type, callable relationships become bidirectional
    with Any.
    """
    # same signature
    a1 = Annotation(Callable[[int], str])
    a2 = Annotation(Callable[[int], str])
    assert a1.is_assignable(a2)
    assert a2.is_assignable(a1)

    # covariant return type (bool is subclass of int)
    a1 = Annotation(Callable[[int], bool])
    a2 = Annotation(Callable[[int], int])
    assert a1.is_assignable(a2)
    assert not a2.is_assignable(a1)

    # contravariant parameters (bool is subclass of int)
    # - Callable[[int], str] accepts any int, including bool so it's a subtype of
    # Callable[[bool], str]
    a1 = Annotation(Callable[[int], str])
    a2 = Annotation(Callable[[bool], str])
    assert a1.is_assignable(a2)
    assert not a2.is_assignable(a1)

    # different parameter count
    a1 = Annotation(Callable[[int], str])
    a2 = Annotation(Callable[[int, int], str])
    assert not a1.is_assignable(a2)
    assert not a2.is_assignable(a1)

    # Callable[..., T] accepts any parameters
    a1 = Annotation(Callable[[int, str], bool])
    a2 = Annotation(Callable[..., bool])
    assert a1.is_assignable(a2)
    assert not a2.is_assignable(a1)

    # return type still matters with ...
    a1 = Annotation(Callable[..., bool])
    a2 = Annotation(Callable[..., int])
    assert a1.is_assignable(a2)  # bool is subclass of int
    assert not a2.is_assignable(a1)

    # Callable with Any in return type - bidirectional due to Any
    a1 = Annotation(Callable[[int], str])
    a2 = Annotation(Callable[[int], Any])
    assert a1.is_assignable(a2)  # str is subtype of Any (covariant + top)
    assert a2.is_assignable(a1)  # Any is subtype of str (bottom type)

    # Callable with Any in parameters - bidirectional due to Any
    a1 = Annotation(Callable[[Any], str])
    a2 = Annotation(Callable[[int], str])
    assert a1.is_assignable(a2)  # Any accepts more (contravariant + bottom)
    assert a2.is_assignable(a1)  # int subtype of Any (top type)

    # Callable[[Any], Any] is bidirectionally related to everything
    a1 = Annotation(Callable[[Any], Any])
    a2 = Annotation(Callable[[int], str])
    assert a1.is_assignable(a2)  # Any dual nature
    assert a2.is_assignable(a1)  # Any dual nature

    # multiple parameters with contravariance
    a1 = Annotation(Callable[[int, str], bool])
    a2 = Annotation(Callable[[bool, str], bool])
    assert a1.is_assignable(a2)
    assert not a2.is_assignable(a1)

    # complex nested types
    a1 = Annotation(Callable[[list[int]], str])
    a2 = Annotation(Callable[[list[bool]], str])
    a3 = Annotation(Callable[[tuple[int]], str])
    a4 = Annotation(Callable[[Sequence[int]], str])
    assert a1.is_assignable(a2)  # list[int] accepts list[bool]
    assert not a2.is_assignable(a1)
    assert not a1.is_assignable(a3)
    assert not a1.is_assignable(a4)
    assert a4.is_assignable(a1)


def test_callable_type_is_assignable():
    """
    Test that type annotations (type[int], type[str], etc.) are recognized as callables.

    Note: The annotation `int` represents instances of int (not callable).
    The annotation `type[int]` represents the type itself (callable).
    """
    # type[int] is like Callable[..., int]
    a1 = Annotation(type[int])
    a2 = Annotation(Callable[[Any], int])
    assert a1.is_assignable(a2)

    # type[int] is also a subclass of Callable[..., int]
    a2 = Annotation(Callable[..., int])
    assert a1.is_assignable(a2)

    # type[int] is a subclass of Callable[[str], int] (broader params)
    a2 = Annotation(Callable[[str], int])
    assert a1.is_assignable(a2)

    # type[int] is NOT a subclass of Callable[[Any], bool] (wrong return type)
    a2 = Annotation(Callable[[Any], bool])
    assert not a1.is_assignable(a2)

    # type[int] is NOT a subclass of Callable[[Any], str] (wrong return type)
    a2 = Annotation(Callable[[Any], str])
    assert not a1.is_assignable(a2)

    # type[str] is like Callable[..., str]
    a1 = Annotation(type[str])
    a2 = Annotation(Callable[[Any], str])
    assert a1.is_assignable(a2)

    # type[list] is like Callable[..., list]
    a1 = Annotation(type[list])
    a2 = Annotation(Callable[[Any], list])
    assert a1.is_assignable(a2)

    # more complex: type[int] with union in Callable
    a1 = Annotation(type[int])
    a2 = Annotation(Callable[[int | str], int])
    assert a1.is_assignable(a2)

    # test with multiple parameters
    a1 = Annotation(type[int])
    a2 = Annotation(Callable[[Any, Any], int])
    assert a1.is_assignable(a2)  # type[int] accepts any number of args

    # but Callable[[Any], int] is NOT a subclass of type[int]
    a1 = Annotation(Callable[[Any], int])
    a2 = Annotation(type[int])
    assert not a1.is_assignable(a2)

    # verify that plain `int` is NOT treated as callable
    a1 = Annotation(int)
    a2 = Annotation(Callable[[Any], int])
    assert not a1.is_assignable(a2)  # int instances are not callable


def test_callable_check_instance():
    """
    Test check_instance for callables.
    """

    def func1(x: int, y: str) -> bool:
        return True

    def func2(x: int) -> str:
        return "test"

    def func3() -> int:
        return 42

    # check basic callable
    a = Annotation(Callable[[int, str], bool])
    assert a.check_instance(func1)
    assert not a.check_instance(func2)  # wrong parameter count
    assert not a.check_instance(func3)  # wrong parameter count
    assert not a.check_instance(123)  # not callable

    # check Callable[..., T]
    a = Annotation(Callable[..., int])
    assert a.check_instance(func1)  # any parameters acceptable
    assert a.check_instance(func2)
    assert a.check_instance(func3)
    assert a.check_instance(lambda: 42)
    assert not a.check_instance("not callable")

    # test with lambda
    a = Annotation(Callable[[int], str])
    assert a.check_instance(lambda x: str(x))
    assert not a.check_instance(lambda x, y: str(x))  # wrong param count

    # test with no parameters
    a = Annotation(Callable[[], int])
    assert a.check_instance(int)
    assert a.check_instance(func3)
    assert a.check_instance(lambda: 42)
    assert not a.check_instance(func1)

    # test with built-in functions (may not have inspectable signature)
    a = Annotation(Callable[..., Any])
    assert a.check_instance(len)
    assert a.check_instance(print)

    # test with classes (they're callable too)
    a = Annotation(Callable[..., Any])
    assert a.check_instance(int)
    assert a.check_instance(str)
    assert a.check_instance(list)

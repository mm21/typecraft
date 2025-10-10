from typing import Any, Literal, Union

from modelingkit.annotation import Annotation

type TestType = list[int]


def test_alias():
    """
    Test normalizing type alias.
    """

    a = Annotation(TestType)
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


def test_is_type():
    """
    Test `Annotation.is_type()` checks.
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


def test_subclass():
    """
    Test basic subclass checks for generics.
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


def test_subclass_union():
    """
    Test subclass checks with unions.
    """

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


def test_subclass_literal():
    """
    Test subclass checks with literals.
    """

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

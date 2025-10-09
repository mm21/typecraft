from typing import Any, Literal

from modelingkit.typing_utils import AnnotationInfo


def test_is_type():
    """
    Test `Annotation.is_type()` checks.
    """

    # non-generics
    a = AnnotationInfo(int)
    assert a.is_type(123)
    assert not a.is_type("123")
    assert not a.is_type([123])

    a = AnnotationInfo(list)
    assert a.is_type([1, "2"])

    a = AnnotationInfo(set)
    assert a.is_type({1, "2"})

    a = AnnotationInfo(tuple)
    assert a.is_type((1, "2"))

    a = AnnotationInfo(dict)
    assert a.is_type({"a": 1})

    # parameterized lists
    a = AnnotationInfo(list[Any])
    assert a.is_type([1, "2"])
    assert a.is_type([])
    assert not a.is_type(1)

    a = AnnotationInfo(list[int])
    assert a.is_type([1, 2])
    assert a.is_type([])
    assert not a.is_type([1, "2"])

    # parameterized set
    a = AnnotationInfo(set[int])
    assert a.is_type({1, 2, 3})
    assert a.is_type(set())
    assert not a.is_type({1, "2"})

    # parameterized fixed-length tuple
    a = AnnotationInfo(tuple[int, str])
    assert a.is_type((1, "2"))
    assert not a.is_type((1, 2))

    # parameterized homogeneous tuple
    a = AnnotationInfo(tuple[int, ...])
    assert a.is_type((1,))
    assert a.is_type((1, 2))
    assert not a.is_type((1, "2"))

    # parameterized dicts
    a = AnnotationInfo(dict[str, int])
    assert a.is_type({"a": 1, "b": 2})
    assert not a.is_type({0: 1})
    assert not a.is_type({"a": "1"})

    a = AnnotationInfo(dict[str, Any])
    assert a.is_type({"a": 1, "b": "2"})
    assert not a.is_type({0: 1})


def test_subclass():
    """
    Test basic subclass checks for generics.
    """

    a1 = AnnotationInfo(int)
    a2 = AnnotationInfo(Any)
    assert a1.is_subclass(a2)
    assert a1.is_subclass(Any)
    assert not a2.is_subclass(a1)

    a1 = AnnotationInfo(list[int])
    a2 = AnnotationInfo(list[Any])
    assert a1.is_subclass(a2)
    assert not a2.is_subclass(a1)

    a1 = AnnotationInfo(list[int])
    a2 = AnnotationInfo(list[float])
    assert not a1.is_subclass(a2)
    assert not a2.is_subclass(a1)

    a1 = AnnotationInfo(list[list[bool]])
    a2 = AnnotationInfo(list[list[int]])
    assert a1.is_subclass(a2)
    assert not a2.is_subclass(a1)

    # list is assumed to be list[Any]
    a1 = AnnotationInfo(list[int])
    a2 = AnnotationInfo(list)
    assert a1.is_subclass(a2)
    assert not a2.is_subclass(a1)

    a1 = AnnotationInfo(list[Any])
    a2 = AnnotationInfo(list)
    assert a1.is_subclass(a2)
    assert a2.is_subclass(a1)


def test_subclass_union():
    """
    Test subclass checks with unions.
    """

    a1 = AnnotationInfo(int)
    a2 = AnnotationInfo(int | str)
    assert a1.is_subclass(a2)
    assert not a2.is_subclass(a1)

    a1 = AnnotationInfo(int | str)
    a2 = AnnotationInfo(int | str | float)
    assert a1.is_subclass(a2)
    assert not a2.is_subclass(a1)

    a1 = AnnotationInfo(list[int | str])
    a2 = AnnotationInfo(list)
    assert a1.is_subclass(a2)
    assert not a2.is_subclass(a1)


def test_subclass_literal():
    """
    Test subclass checks with literals.
    """

    a1 = AnnotationInfo(Literal["a"])
    a2 = AnnotationInfo(Literal["a", "b"])
    assert a1.is_subclass(a2)
    assert not a2.is_subclass(a1)

    a2 = AnnotationInfo(str)
    assert a1.is_subclass(a2)
    assert not a2.is_subclass(a1)

    a3 = AnnotationInfo(Literal["a", "b"] | int)
    a4 = AnnotationInfo(int)
    assert a1.is_subclass(a3)
    assert a4.is_subclass(a3)
    assert not a3.is_subclass(a1)
    assert not a3.is_subclass(a4)

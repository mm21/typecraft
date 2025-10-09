from typing import Any

from modelingkit.typing_utils import AnnotationInfo


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
    a2 = AnnotationInfo(int | bool)
    assert a1.is_subclass(a2)
    assert not a2.is_subclass(a1)

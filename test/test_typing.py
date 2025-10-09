from typing import Any

from modelingkit.typing_utils import AnnotationInfo


def test_subclass():
    """
    Test subclass detection of generics.
    """

    t1 = AnnotationInfo(list[int])
    t2 = AnnotationInfo(list[Any])
    assert t1.is_subclass(t2)
    assert not t2.is_subclass(t1)

    t1 = AnnotationInfo(list[int])
    t2 = AnnotationInfo(list[float])
    assert not t1.is_subclass(t2)
    assert not t2.is_subclass(t1)

    t1 = AnnotationInfo(list[list[bool]])
    t2 = AnnotationInfo(list[list[int]])
    assert t1.is_subclass(t2)
    assert not t2.is_subclass(t1)

    # list is assumed to be list[Any]
    t1 = AnnotationInfo(list[int])
    t2 = AnnotationInfo(list)
    assert t1.is_subclass(t2)
    assert not t2.is_subclass(t1)

    t1 = AnnotationInfo(list[Any])
    t2 = AnnotationInfo(list)
    assert t1.is_subclass(t2)
    assert t2.is_subclass(t1)

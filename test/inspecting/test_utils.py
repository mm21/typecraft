"""
Tests for low-level annotation utilities.
"""

from types import EllipsisType, NoneType, UnionType
from typing import Annotated, Any, Literal, Union, get_args, get_origin

from modelingkit.inspecting import (
    Annotation,
    flatten_union,
    get_concrete_type,
    is_instance,
    is_subtype,
    is_union,
    normalize_annotation,
    split_annotated,
    unwrap_alias,
)

type SimpleAlias = int
type UnionAlias = int | str
type LegacyUnionAlias = Union[int, str]
type AnnotatedAlias = Annotated[int, "doc"]
type ListAlias = list[int]
type AnnotatedListAlias = Annotated[ListAlias, "doc"]
type UnionWithAnnotatedAlias = Union[Annotated[int, "positive"], str]
type DeepAlias = Annotated[Union[int, str], "constraint"]


def test_is_subclass():
    # verify all overloads
    assert is_subtype(Annotation(int), Annotation(Any))
    assert is_subtype(Annotation(int), Any)
    assert is_subtype(int, Annotation(Any))
    assert is_subtype(int, Any)

    # verify with alias
    assert is_subtype(SimpleAlias, UnionAlias)
    assert is_subtype(ListAlias, AnnotatedListAlias)


def test_is_instance():
    # verify all overloads
    assert is_instance(1, Any)
    assert is_instance(1, int)
    assert is_instance(1, Annotation(Any))
    assert is_instance(1, Annotation(int))

    # verify with alias
    assert is_instance(1, UnionAlias)
    assert is_instance([1], ListAlias)


def test_unwrap_alias():
    # non-alias types should pass through unchanged
    assert unwrap_alias(int) is int
    assert unwrap_alias(str) is str

    annotation = unwrap_alias(list[int])
    assert get_origin(annotation) is list
    assert get_args(annotation)[0] is int

    # aliases should be unwrapped
    assert unwrap_alias(SimpleAlias) is int
    assert unwrap_alias(LegacyUnionAlias) == Union[int, str]


def test_split_annotated():
    # non-annotated should return empty extras
    annotation, extras = split_annotated(int)
    assert annotation is int
    assert extras == ()

    # annotated with single extra
    annotation, extras = split_annotated(Annotated[int, "doc"])
    assert annotation is int
    assert extras == ("doc",)

    # annotated with multiple extras
    annotation, extras = split_annotated(Annotated[str, "doc", 42, None])
    assert annotation is str
    assert extras == ("doc", 42, None)

    # nested types
    annotation, extras = split_annotated(Annotated[list[int], "doc"])
    assert get_origin(annotation) is list
    assert get_args(annotation)[0] is int
    assert extras == ("doc",)


def test_is_union():
    # modern union syntax (int | str)
    assert is_union(int | str)
    assert is_union(int | str | None)

    # legacy union syntax
    assert is_union(Union[int, str])
    assert is_union(Union[int, str, None])

    # non-unions
    assert not is_union(int)
    assert not is_union(str)
    assert not is_union(list[int])
    assert not is_union(Annotated[int, "doc"])

    # edge case: union with single type is normalized by typing module
    single_union = Union[int]
    assert single_union is int  # union[int] normalizes to int
    assert not is_union(single_union)


def test_normalize_annotation():
    # simple types pass through
    assert normalize_annotation(int) is int
    assert normalize_annotation(str) is str

    # unwrap alias
    assert normalize_annotation(SimpleAlias) is int

    # unwrap annotated (preserve_extras=False)
    assert normalize_annotation(Annotated[int, "doc"]) is int
    assert normalize_annotation(Annotated[str, "doc", 42]) is str

    # preserve annotated (preserve_extras=True)
    annotated_type = Annotated[int, "doc"]
    assert normalize_annotation(annotated_type, preserve_extras=True) is annotated_type

    # unwrap both alias and annotated
    assert normalize_annotation(AnnotatedAlias) is int

    # complex nested case
    annotation = normalize_annotation(AnnotatedListAlias)
    assert get_origin(annotation) is list
    assert get_args(annotation)[0] is int


def test_flatten_union():
    # modern union syntax
    result = flatten_union(int | str)
    assert result == (int, str)

    # legacy union syntax
    result = flatten_union(Union[int, str])
    assert result == (int, str)

    # non-union returns single-element tuple
    assert flatten_union(int) == (int,)
    assert flatten_union(str) == (str,)

    # nested unions should flatten
    result = flatten_union(Union[int, Union[str, float]])
    assert result == (int, str, float)

    # modern nested unions
    result = flatten_union(int | (str | float))
    assert result == (int, str, float)

    # union with None (optional)
    result = flatten_union(int | None)
    assert result[0] is int
    assert result[1] is NoneType

    # unwrap aliases in union
    result = flatten_union(Union[SimpleAlias, str])
    assert result == (int, str)


def test_flatten_union_with_annotated():
    # annotated in union (preserve_extras=False)
    result = flatten_union(Union[Annotated[int, "doc"], str])
    assert result == (int, str)

    # annotated in union (preserve_extras=True)
    result = flatten_union(Union[Annotated[int, "doc"], str], preserve_extras=True)
    assert len(result) == 2
    assert get_origin(result[0]) is Annotated
    assert result[1] is str


def test_get_concrete_type():
    # simple types
    assert get_concrete_type(int) is int
    assert get_concrete_type(str) is str

    # parameterized generics
    assert get_concrete_type(list[int]) is list
    assert get_concrete_type(dict[str, int]) is dict
    assert get_concrete_type(tuple[int, ...]) is tuple

    # unwrap alias
    assert get_concrete_type(SimpleAlias) is int

    # unwrap annotated
    assert get_concrete_type(Annotated[int, "doc"]) is int
    assert get_concrete_type(Annotated[list[int], "doc"]) is list

    # special cases return object
    assert get_concrete_type(Literal[1, 2, 3]) is object
    assert get_concrete_type(Any) is object

    # singleton mapping
    assert get_concrete_type(None) is NoneType
    assert get_concrete_type(type(None)) is NoneType
    assert get_concrete_type(Ellipsis) is EllipsisType
    assert get_concrete_type(type(Ellipsis)) is EllipsisType

    # union types
    assert get_concrete_type(int | str) is UnionType
    assert get_concrete_type(Union[int, str]) is UnionType

    # complex nested case
    assert get_concrete_type(Annotated[list[int], "doc"]) is list
    assert get_concrete_type(ListAlias) is list


def test_compositions():
    # alias of union with annotated
    normalized = normalize_annotation(UnionWithAnnotatedAlias)
    assert is_union(normalized)

    flattened = flatten_union(UnionWithAnnotatedAlias)
    assert flattened == (int, str)

    # deeply nested
    normalized = normalize_annotation(DeepAlias)
    assert is_union(normalized)

    flattened = flatten_union(DeepAlias)
    assert flattened == (int, str)


def test_edge_cases():
    # empty-like cases shouldn't crash
    assert not is_union(type(None))
    assert get_concrete_type(type(None)) is NoneType

    # ellipsis
    assert get_concrete_type(type(...)) is EllipsisType

    # mixed union syntaxes in nested structures
    result = flatten_union(Union[int | str, float])
    assert result == (int, str, float)

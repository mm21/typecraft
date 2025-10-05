from __future__ import annotations

from functools import cached_property
from types import EllipsisType, GenericAlias, NoneType, UnionType
from typing import (
    Annotated,
    Any,
    Literal,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
    overload,
)

__all__ = [
    "AnnotationInfo",
    "split_annotated",
    "is_union",
    "flatten_union",
    "get_concrete_type",
    "get_type_param",
]

type AnnotationType = type[Any] | GenericAlias | UnionType | EllipsisType
type RawAnnotationType = AnnotationType | Annotated


class AnnotationInfo:
    """
    Performs normalizations on annotation and encapsulates useful info.
    """

    annotation: AnnotationType
    """
    Original annotation after stripping `Annotated[]` if applicable. May be a generic
    type.
    """

    extras: tuple[Any, ...]
    """
    Extra annotations, if `Annotated[]` was passed.
    """

    origin: Any
    """
    Origin, non-`None` if annotation is a generic type.
    """

    args: tuple[AnnotationInfo, ...]
    """
    Type parameters, if annotation is a generic type and `origin` is not `Literal`.
    """

    concrete_type: type
    """
    Concrete (non-generic) type, determined based on annotation:
    
    - Generic type: `get_origin(annotation)`
    - Union: `UnionType`
    - Literal: `object`
    - Otherwise: annotation itself, ensuring it's a type
    """

    def __init__(self, raw_annotation: RawAnnotationType, /):
        annotation, extras = split_annotated(raw_annotation)

        self.annotation = annotation
        self.extras = extras
        self.origin = get_origin(annotation)
        self.args = (
            tuple(AnnotationInfo(a) for a in get_args(annotation))
            if self.origin is not Literal
            else ()
        )
        self.concrete_type = get_concrete_type(annotation)

    def __repr__(self) -> str:
        annotation = f"annotation={self.annotation}"
        extras = f"extras={self.extras}"
        origin = f"origin={self.origin}"
        args = f"args={self.args}"
        concrete_type = f"concrete_type={self.concrete_type}"
        return (
            f"AnnotationInfo({annotation}, {extras}, {origin}, {args}, {concrete_type})"
        )

    @property
    def is_union(self) -> bool:
        return self.concrete_type is UnionType

    @property
    def is_literal(self) -> bool:
        return self.origin is Literal

    # TODO: delete
    @property
    def union_types(self) -> tuple[type, ...]:
        """
        Concrete types of union, if `is_union`.
        """
        if self.is_union:
            return tuple(a.concrete_type for a in self.args)
        else:
            return (self.concrete_type,)

    @cached_property
    def literal_values(self) -> tuple[Any, ...]:
        """
        Value(s) of literal, if `is_literal`.
        """
        if self.is_literal:
            values = get_args(self.annotation)
            assert len(values)
            return values
        else:
            return ()


def split_annotated(
    raw_annotation: RawAnnotationType, /
) -> tuple[AnnotationType, tuple[RawAnnotationType, ...]]:
    """
    Split Annotated[x, ...] (if present) into annotation and extras.
    """
    if get_origin(raw_annotation) is Annotated:
        args = get_args(raw_annotation)
        assert len(args)

        annotation = args[0]
        extras = tuple(args[1:])
    else:
        annotation = raw_annotation
        extras = ()

    return annotation, extras


def is_union(raw_annotation: RawAnnotationType, /) -> bool:
    """
    Check whether the annotation is a union.
    """
    annotation, _ = split_annotated(raw_annotation)
    return isinstance(annotation, UnionType) or get_origin(annotation) is Union


def flatten_union(
    raw_annotation: RawAnnotationType, /
) -> tuple[RawAnnotationType, ...]:
    """
    Flatten union (if present) into its constituent types.
    """
    annotation, _ = split_annotated(raw_annotation)
    return get_args(annotation) if is_union(annotation) else (annotation,)


def get_concrete_type(raw_annotation: RawAnnotationType, /) -> type:
    """
    Get concrete type of parameterized annotation, or `object` if the annotation is
    a literal.
    """
    annotation, _ = split_annotated(raw_annotation)
    concrete_type = get_origin(annotation) or annotation

    if concrete_type is Literal:
        return object

    # convert singletons to respective type so isinstance() works as expected
    singleton_map = {None: NoneType, Ellipsis: EllipsisType, Union: UnionType}
    concrete_type = singleton_map.get(concrete_type, concrete_type)

    assert isinstance(
        concrete_type, type
    ), f"Not a type: '{concrete_type}' (from annotation '{annotation}')"

    return concrete_type


@overload
def get_type_param[BaseT](cls: type[Any], base_cls: type[BaseT]) -> type | None: ...


@overload
def get_type_param[BaseT, ParamT](
    cls: type[Any], base_cls: type[BaseT], param_base_cls: type[ParamT]
) -> type[ParamT] | None: ...


# TODO: pass index of desired param to differentiate multiple type params of the
# same type
def get_type_param[BaseT, ParamT](
    cls: type[Any], base_cls: type[BaseT], param_base_cls: type[ParamT] | None = None
) -> type[ParamT] | type | None:
    """
    Extract the concrete type param from the given base class. If `base_cls` can be
    parameterized with multiple types, it's recommend to also pass `param_base_cls`
    to get the desired type param.
    """

    def check_origin(origin: Any) -> bool:
        return (
            origin is not None
            and isinstance(origin, type)
            and issubclass(origin, base_cls)
        )

    def check_arg(arg: Any) -> bool:
        if arg is None or not isinstance(arg, type):
            return False
        elif param_base_cls and not issubclass(arg, param_base_cls):
            return False
        else:
            return True

    def get_bases(cls: type, attr: str) -> list[type]:
        return list(cast(tuple[type], getattr(cls, attr, ())))

    def get_arg(cls: type) -> type[ParamT] | type | None:
        # check pydantic metadata if applicable
        if metadata := getattr(cls, "__pydantic_generic_metadata__", None):
            origin, args = metadata["origin"], metadata["args"]
        else:
            origin, args = get_origin(cls), get_args(cls)

        if check_origin(origin):
            for arg in args:
                # TODO: check TypeVar bound, but prioritize concrete type?
                if isinstance(arg, TypeVar):
                    continue

                if check_arg(arg):
                    return arg

        # not found, recurse into bases
        for base in get_bases(cls, "__orig_bases__") + get_bases(cls, "__bases__"):
            if param := get_arg(base):
                return param

        return None

    return get_arg(cls)

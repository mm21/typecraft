from __future__ import annotations

from types import EllipsisType, NoneType, UnionType
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


class AnnotationInfo:
    """
    Performs normalizations on annotation and encapsulates useful info.
    """

    annotation: Any
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

    args: tuple[Any, ...]
    """
    Type parameters.
    """

    args_info: tuple[AnnotationInfo, ...]
    """
    Annotation info for type parameters, if not `is_literal`.
    """

    concrete_type: type
    """
    Concrete (non-generic) type, determined based on annotation:
    
    - Generic type: `get_origin(annotation)`
    - Union: `UnionType`
    - Literal: `object`
    - Otherwise: annotation itself, ensuring it's a type
    """

    def __init__(self, annotation: Any, /):
        annotation_, extras = split_annotated(annotation)

        self.annotation = annotation_
        self.extras = extras
        self.origin = get_origin(annotation_)
        self.args = get_args(annotation_)
        self.args_info = (
            tuple(AnnotationInfo(a) for a in self.args)
            if self.origin is not Literal
            else ()
        )
        self.concrete_type = get_concrete_type(annotation_)

    def __repr__(self) -> str:
        annotation = f"annotation={self.annotation}"
        extras = f"extras={self.extras}"
        origin = f"origin={self.origin}"
        args = f"args={self.args_info}"
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

    def is_subclass(self, other: AnnotationInfo):
        """
        Check if this annotation is a "subclass" of other; e.g. would return `True` for
        `AnnotationInfo(list[int]).is_subclass(list[Any])` since `int` is a "subclass"
        of `Any`.
        """

        # check concrete type
        if not issubclass(self.concrete_type, other.concrete_type):
            return False

        other_args = other.args_info

        # missing args assumed to be Any
        # - no need to pad args if other has more args; my args will always be a
        # subset of Any
        if len(self.args_info) < len(other.args_info):
            my_args = list(self.args_info) + [AnnotationInfo(Any)] * (
                len(other.args_info) - len(self.args_info)
            )
        else:
            my_args = self.args_info

        # recurse into args
        for my_arg, other_arg in zip(my_args, other_args):
            if not my_arg.is_subclass(other_arg):
                return False

        return True


def split_annotated(annotation: Any, /) -> tuple[Any, tuple[Any, ...]]:
    """
    Split Annotated[x, ...] (if present) into annotation and extras.
    """
    if get_origin(annotation) is Annotated:
        args = get_args(annotation)
        assert len(args)

        annotation_ = args[0]
        extras = tuple(args[1:])
    else:
        annotation_ = annotation
        extras = ()

    return annotation_, extras


def is_union(annotation: Any, /) -> bool:
    """
    Check whether the annotation is a union.
    """
    annotation_, _ = split_annotated(annotation)
    return isinstance(annotation_, UnionType) or get_origin(annotation_) is Union


def flatten_union(annotation: Any, /) -> tuple[Any, ...]:
    """
    Flatten union (if present) into its constituent types.
    """
    annotation_, _ = split_annotated(annotation)
    return get_args(annotation_) if is_union(annotation_) else (annotation_,)


def get_concrete_type(annotation: Any, /) -> type:
    """
    Get concrete type of parameterized annotation, or `object` if the annotation is
    a literal or `Any`.
    """
    annotation_, _ = split_annotated(annotation)
    concrete_type = get_origin(annotation_) or annotation_

    if concrete_type in {Literal, Any}:
        return object

    # convert singletons to respective type so isinstance() works as expected
    singleton_map = {None: NoneType, Ellipsis: EllipsisType, Union: UnionType}
    concrete_type = singleton_map.get(concrete_type, concrete_type)

    assert isinstance(
        concrete_type, type
    ), f"Not a type: '{concrete_type}' (from annotation '{annotation_}')"

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

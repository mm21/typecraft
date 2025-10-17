"""
Utilities to inspect annotations.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable as CallableABC
from types import EllipsisType, NoneType, UnionType
from typing import (
    Annotated,
    Any,
    Literal,
    TypeAliasType,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
    overload,
)

__all__ = [
    "Annotation",
    "unwrap_alias",
    "split_annotated",
    "is_union",
    "normalize_annotation",
    "flatten_union",
    "get_concrete_type",
    "get_type_param",
]


class Annotation:
    """
    Comprehensive representation of an annotation with interfaces to determine
    relationships to objects (`isinstance()`-like) and other annotations
    (`issubclass()`-like).

    Unwraps `TypeAlias` and `Annotated` if applicable.
    """

    raw: Any
    """
    Original annotation after stripping `Annotated[]` if applicable. May be a generic
    type.
    """

    extras: tuple[Any, ...]
    """
    Annotation extras, if `Annotated[]` was passed.
    """

    origin: Any
    """
    Origin, non-`None` if annotation is a generic type.
    """

    args: tuple[Any, ...]
    """
    Generic type parameters.
    """

    arg_annotations: tuple[Annotation, ...]
    """
    Annotation info for generic type parameters, only applicable if annotation is not
    `Literal[]` or `Callable[]`.
    """

    param_annotations: tuple[Annotation, ...] | None = None
    """
    For callable types, annotations for the parameters.
    `None` if Callable[..., ReturnType].
    """

    return_annotation: Annotation | None = None
    """
    For callable types, annotation for the return type.
    """

    concrete_type: type
    """
    Concrete (non-generic) type, determined based on annotation:
    
    - `Any` or `Literal`: `object`
    - `None`: `NoneType`
    - `Ellipsis`: `EllipsisType`
    - `Union`: `UnionType`
    - Generic type: `get_origin(annotation)`
    - Otherwise: annotation itself, ensuring it's a type
    """

    def __init__(self, annotation: Any, /):
        raw, extras = split_annotated(unwrap_alias(annotation))
        raw = unwrap_alias(raw)

        self.raw = raw
        self.extras = extras
        self.origin = get_origin(raw)
        self.args = get_args(raw)

        # handle callable-specific attributes
        if self.origin is CallableABC and self.args:
            # args is like ([int, str], bool) or (..., bool)
            assert len(self.args) == 2
            params, return_type = self.args
            if params is not ...:
                self.param_annotations = tuple(Annotation(p) for p in params)
            self.return_annotation = Annotation(return_type)

        self.arg_annotations = (
            tuple(Annotation(a) for a in self.args)
            if self.origin not in (Literal, CallableABC)
            else ()
        )
        self.concrete_type = get_concrete_type(raw)

    def __repr__(self) -> str:
        raw = f"{self.raw}"
        extras = f"extras={self.extras}"
        origin = f"origin={self.origin}"
        args = f"args={self.args}"
        concrete_type = f"concrete_type={self.concrete_type}"
        return f"Annotation({", ".join((raw, extras, origin, args, concrete_type))})"

    def __eq__(self, other: Any, /) -> bool:
        if not isinstance(other, Annotation):
            return False
        return self.is_subclass(other) and other.is_subclass(self)

    @property
    def is_union(self) -> bool:
        return self.concrete_type is UnionType

    @property
    def is_literal(self) -> bool:
        return self.origin is Literal

    @property
    def is_callable(self) -> bool:
        return self.origin is CallableABC

    @overload
    def is_subclass(self, other: Annotation, /) -> bool: ...

    @overload
    def is_subclass(self, other: Any, /) -> bool: ...

    def is_subclass(self, other: Any, /) -> bool:
        """
        Check if this annotation is a "subclass" of other annotation; loosely
        equivalent to `issubclass(annotation, other)`.

        Examples:

        - `Annotation(int).is_subclass(Annotation(Any))` returns `True`
        - `Annotation(list[int]).is_subclass(list[Any])` returns `True`
        - `Annotation(list[int]).is_subclass(list[str])` returns `False`
        - `Annotation(int).is_subclass(Callable[[Any], int])` returns `True`
        """
        other_ann = other if isinstance(other, Annotation) else Annotation(other)

        # handle union for self
        if self.is_union:
            return all(a.is_subclass(other_ann) for a in self.arg_annotations)

        # handle union for other
        if other_ann.is_union:
            return any(self.is_subclass(a) for a in other_ann.arg_annotations)

        # handle literal for self
        if self.is_literal:
            return all(other_ann.is_type(value) for value in self.args)

        # handle literal for other: non-literal can never be a "subclass" of literal
        if other_ann.is_literal:
            return False

        # handle callables
        if self.is_callable or other_ann.is_callable:
            if not self.is_callable and other_ann.is_callable:
                # callable type (e.g., int, str) being compared to Callable
                return self._is_subclass_callable_type(other_ann)
            return self._is_subclass_callable(other_ann)

        # check concrete type
        if not issubclass(self.concrete_type, other_ann.concrete_type):
            return False

        # concrete type matches, check args
        other_args = other_ann.arg_annotations

        # pad missing args in self, assumed to be Any
        # - no need to pad if other has more args; my args will always be a
        # subset of Any
        if len(self.arg_annotations) < len(other_args):
            my_args = list(self.arg_annotations) + [ANY_ANNOTATION] * (
                len(other_args) - len(self.arg_annotations)
            )
        else:
            my_args = self.arg_annotations

        # recurse into args
        for my_arg, other_arg in zip(my_args, other_args):
            if not my_arg.is_subclass(other_arg):
                return False

        return True

    def _is_subclass_callable(self, other: Annotation) -> bool:
        """
        Check if this callable is a subclass of another callable.

        Callables are contravariant in parameters and covariant in return type.
        """
        if not (self.is_callable and other.is_callable):
            return False
        assert self.return_annotation and other.return_annotation

        # handle ... parameters (any parameters acceptable)
        if other.param_annotations is None:
            # other accepts any params, check return type only
            return self.return_annotation.is_subclass(other.return_annotation)

        if self.param_annotations is None:
            # we accept any params, but other doesn't - not a subclass
            return False

        # both have specific parameters
        if len(self.param_annotations) != len(other.param_annotations):
            return False

        # check parameters (contravariant - reversed)
        for my_param, other_param in zip(
            self.param_annotations, other.param_annotations
        ):
            if not other_param.is_subclass(my_param):
                return False

        return self.return_annotation.is_subclass(other.return_annotation)

    def _is_subclass_callable_type(self, other: Annotation) -> bool:
        """
        Check if this type annotation (e.g., type[int], type[str]) is a subclass of a
        Callable annotation. Treats self as Callable[..., X] where X is the type
        parameter (accepts any parameters, returns instances of X).

        Note: The annotation `int` represents instances of int (not callable).
        The annotation `type[int]` represents the type itself (callable).
        """
        # only type[X] annotations represent callable types
        if self.origin is not type:
            return False

        assert not self.is_callable and other.is_callable
        assert other.return_annotation is not None

        # we're effectively Callable[..., X] where X is our type parameter
        # - get the type parameter (e.g., int from type[int])
        if len(self.arg_annotations) == 0:
            # just bare `type`, which is Callable[..., object]
            return_ann = Annotation(object)
        else:
            return_ann = self.arg_annotations[0]

        # With ... parameters, we accept any parameters, so contravariance always satisfied
        return return_ann.is_subclass(other.return_annotation)

    def is_type(self, obj: Any) -> bool:
        """
        Check if object is an instance of this annotation; loosely equivalent to
        `isinstance(obj, annotation)`.

        Examples:

        - `Annotation(Any).is_type(1)` returns `True`
        - `Annotation(list[int]).is_type([1, 2, 3])` returns `True`
        - `Annotation(list[int]).is_type([1, 2, "3"])` returns `False`
        """
        if self.is_literal:
            return any(obj == value for value in self.args)

        if self.is_union:
            return any(a.is_type(obj) for a in self.arg_annotations)

        if self.is_callable:
            return self._check_callable(obj)

        if not isinstance(obj, self.concrete_type):
            return False

        if issubclass(self.concrete_type, (list, tuple, set, dict)):
            return self._check_collection(obj)

        # concrete type matches and is not a collection
        return True

    def _check_callable(self, obj: Any) -> bool:
        """
        Check if object matches this callable annotation.
        """
        if not callable(obj):
            return False

        # If Callable[..., ReturnType], just check it's callable
        if self.param_annotations is None:
            return True

        # Try to validate parameter count
        try:
            sig = inspect.signature(obj)
            # Count positional and positional-or-keyword parameters
            param_count = sum(
                1
                for p in sig.parameters.values()
                if p.kind
                in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                )
            )

            return param_count == len(self.param_annotations)
        except (ValueError, TypeError):
            # Can't get signature (e.g., built-in functions), assume it's fine
            return True

    def _check_collection(self, obj: Any) -> bool:
        """
        Recursively check if object matches this collection's annotation.
        """
        assert isinstance(obj, self.concrete_type)

        if isinstance(obj, (list, set)):
            return self._check_list_or_set(obj)
        elif isinstance(obj, tuple):
            return self._check_tuple(obj)
        else:
            assert isinstance(obj, dict)
            return self._check_dict(obj)

    def _check_list_or_set(self, obj: list[Any] | set[Any]) -> bool:
        assert len(self.arg_annotations) in {0, 1}
        ann = self.arg_annotations[0] if len(self.arg_annotations) else ANY_ANNOTATION

        return all(ann.is_type(o) for o in obj)

    def _check_tuple(self, obj: tuple[Any]) -> bool:
        if len(self.arg_annotations) and self.arg_annotations[-1].raw is not ...:
            # fixed-length tuple like tuple[int, str, float]
            return all(a.is_type(o) for a, o in zip(self.arg_annotations, obj))
        else:
            # homogeneous tuple like tuple[int, ...]
            assert len(self.arg_annotations) in {0, 2}
            ann = (
                self.arg_annotations[0] if len(self.arg_annotations) else ANY_ANNOTATION
            )

            return all(ann.is_type(o) for o in obj)

    def _check_dict(self, obj: dict[Any, Any]) -> bool:
        assert len(self.arg_annotations) in {0, 2}
        key_ann, value_ann = (
            self.arg_annotations
            if len(self.arg_annotations) == 2
            else (ANY_ANNOTATION, ANY_ANNOTATION)
        )

        return all(key_ann.is_type(k) and value_ann.is_type(v) for k, v in obj.items())


@overload
def is_subclass(annotation: Annotation, other: Annotation) -> bool: ...


@overload
def is_subclass(annotation: Annotation, other: Any) -> bool: ...


@overload
def is_subclass(annotation: Any, other: Annotation) -> bool: ...


@overload
def is_subclass(annotation: Any, other: Any) -> bool: ...


def is_subclass(annotation: Any, other: Any) -> bool:
    """
    Return whether annotation is a "subclass" of other annotation.

    Accommodates generic types and fully resolves type aliases, unions, and
    `Annotated`.
    """
    ann = annotation if isinstance(annotation, Annotation) else Annotation(annotation)
    return ann.is_subclass(other)


@overload
def is_instance(obj: Any, annotation: Annotation) -> bool: ...


@overload
def is_instance(obj: Any, annotation: Any) -> bool: ...


def is_instance(obj: Any, annotation: Any) -> bool:
    """
    Return whether an object is an "instance" of an annotation.

    Accommodates generic types and fully resolves type aliases, unions, and
    `Annotated`.
    """
    ann = annotation if isinstance(annotation, Annotation) else Annotation(annotation)
    return ann.is_type(obj)


def unwrap_alias(annotation: Any, /) -> Any:
    """
    If annotation is a `TypeAlias`, extract the corresponding definition.
    """
    return annotation.__value__ if isinstance(annotation, TypeAliasType) else annotation


def split_annotated(annotation: Any, /) -> tuple[Any, tuple[Any, ...]]:
    """
    If annotation is an `Annotated`, split it into the wrapped annotation and extras.
    """
    if get_origin(annotation) is Annotated:
        args = get_args(annotation)
        assert len(args)
        return args[0], tuple(args[1:])
    return annotation, ()


def is_union(annotation: Any, /) -> bool:
    """
    Check whether annotation is a union, accommodating both `int | str`
    and `Union[int, str]`.
    """
    return isinstance(annotation, UnionType) or get_origin(annotation) is Union


def normalize_annotation(annotation: Any, /, *, preserve_extras: bool = False) -> Any:
    """
    Fully normalize annotation:

    - Unwrap aliases
    - If `preserve_extras` is `False`, unwrap `Annotated` and discard extras
    """
    annotation_ = unwrap_alias(annotation)
    if get_origin(annotation_) is Annotated and not preserve_extras:
        annotation_, _ = split_annotated(annotation_)
        annotation_ = unwrap_alias(annotation_)  # Annotated[] might wrap an alias
    return annotation_


def flatten_union(
    annotation: Any, /, *, preserve_extras: bool = False
) -> tuple[Any, ...]:
    """
    If annotation is a union, recursively flatten it into its constituent types;
    otherwise return the annotation as-is. If `preserve_extras` is `True`, don't
    recurse into unions wrapped by `Annotated[]`.

    Unwraps aliases at each recursion.
    """
    return tuple(_recurse_union(annotation, preserve_extras=preserve_extras))


def get_concrete_type(annotation: Any, /) -> type:
    """
    Get concrete type of parameterized annotation, or `object` if the annotation is
    a `Literal` or `Any`.

    Unwraps aliases and `Annotated`.
    """
    annotation_ = normalize_annotation(annotation)
    concrete_type = get_origin(annotation_) or annotation_

    if concrete_type in {Literal, Any}:
        return object

    # convert singletons to respective type so isinstance() works as expected
    singleton_map = {None: NoneType, Ellipsis: EllipsisType, Union: UnionType}
    concrete_type = singleton_map.get(concrete_type, concrete_type)

    assert isinstance(
        concrete_type, type
    ), f"Not a type: '{concrete_type}' (from annotation '{annotation}' normalized to '{annotation_}')"

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


def _recurse_union(annotation: Any, /, *, preserve_extras: bool) -> list[Any]:
    args: list[Any] = []
    annotation_ = normalize_annotation(annotation, preserve_extras=preserve_extras)

    if is_union(annotation_):
        for a in get_args(annotation_):
            args += _recurse_union(a, preserve_extras=preserve_extras)
    else:
        args.append(annotation_)

    return args


ANY_ANNOTATION = Annotation(Any)
"""
Annotation encapsulating `Any`.
"""

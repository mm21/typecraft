"""
Utilities to inspect type annotations.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from inspect import Parameter
from types import EllipsisType, GenericAlias, NoneType, UnionType
from typing import (
    Annotated,
    Any,
    Literal,
    Self,
    TypeAliasType,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
)

from .generics import extract_args, normalize_args
from .utils import robust_issubclass

__all__ = [
    "ANY",
    "Annotation",
    "is_subtype",
    "is_instance",
    "is_union",
    "unwrap_alias",
    "split_annotated",
    "normalize_annotation",
    "flatten_union",
    "get_concrete_type",
]

LiteralType = type(Literal["sentinel"])


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

    __cache: dict[int, Self] = {}
    """
    Cache to prevent infinite recursion with recursive type aliases.
    """

    __init_done: bool = False
    """
    Whether initialization has already been completed.
    """

    def __new__(cls, annotation: Any, /) -> Self:
        """
        Create or retrieve cached Annotation instance to support recursive type aliases.
        """
        key = id(annotation)

        if obj := cls.__cache.get(key):
            return obj

        obj = super().__new__(cls)
        cls.__cache[key] = obj
        return obj

    def __init__(self, annotation: Any, /):
        # skip initialization if already done or in progress (cached instance)
        if self.__init_done:
            return

        self.__init_done = True
        raw, extras = split_annotated(unwrap_alias(annotation))
        raw = unwrap_alias(raw)

        self.raw = raw
        self.extras = extras
        self.origin = get_origin(raw)
        self.args = get_args(raw)

        # handle callable-specific attributes
        if self.origin is Callable and self.args:
            # args is like ([int, str], bool) or (..., bool)
            assert len(self.args) == 2
            params, return_type = self.args
            if params is not ...:
                self.param_annotations = tuple(Annotation(p) for p in params)
            self.return_annotation = Annotation(return_type)

        self.arg_annotations = (
            tuple(Annotation(a) for a in self.args)
            if self.origin not in (Literal, Callable)
            else cast(tuple[Annotation, ...], ())
        )
        self.concrete_type = get_concrete_type(raw)

        # validate tuple if applicable
        if issubclass(self.concrete_type, tuple) and len(self.arg_annotations):
            if self.arg_annotations[-1].raw is ...:
                if len(self.arg_annotations) != 2 or self.arg_annotations[0].raw is ...:
                    raise ValueError(f"Invalid variadic tuple: {annotation}")

    def __repr__(self) -> str:
        raw = f"{self.raw}"
        extras = f"extras={self.extras}"
        concrete_type = f"concrete_type={self.concrete_type}"
        return f"Annotation({", ".join((raw, extras, concrete_type))})"

    def __eq__(self, other: Any, /) -> bool:
        if not isinstance(other, Annotation):
            return False
        return self.equals(other)

    def equals(self, other: Annotation, /, *, match_any: bool = False) -> bool:
        if self is other:
            return True
        if match_any and (self.raw is Any or other.raw is Any):
            return True
        if self.concrete_type is not other.concrete_type:
            return False

        my_args = list(self.arg_annotations)
        other_args = list(other.arg_annotations)

        if len(my_args) < len(other_args):
            my_args += [ANY] * (len(other_args) - len(my_args))
        elif len(other_args) < len(my_args):
            my_args += [ANY] * (len(my_args) - len(other_args))

        return all(
            my_arg.equals(other_arg, match_any=match_any)
            for my_arg, other_arg in zip(my_args, other_args)
        )

    @property
    def is_union(self) -> bool:
        return self.concrete_type is UnionType

    @property
    def is_literal(self) -> bool:
        return self.origin is Literal

    @property
    def is_callable(self) -> bool:
        return self.origin is Callable

    def is_subtype(self, other: Annotation | Any, /) -> bool:
        """
        Check if this annotation is a subtype of other annotation; roughly
        equivalent to `issubclass(annotation, other)`.

        Any is BOTH a top type and a bottom type in Python's gradual typing:
        - Top type: Everything is a subtype of Any (you can assign anything TO Any)
        - Bottom type: Any is a subtype of everything (you can assign anything FROM Any)

        `object` is a concrete type - only actual object subtypes are subtypes of
        `object`.

        Examples:

        - `Annotation(int).is_subtype(Annotation(Any))` returns `True` (Any as top type)
        - `Annotation(Any).is_subtype(Annotation(int))` returns `True` (Any as bottom type)
        - `Annotation(list[int]).is_subtype(list[Any])` returns `True`
        - `Annotation(list[Any]).is_subtype(list[int])` returns `True` (Any in params)
        - `Annotation(int).is_subtype(Callable[[Any], int])` returns `True`
        """
        other_ann = Annotation._normalize(other)

        # Any is the top type - everything is a subtype of Any
        if other_ann.raw is Any:
            return True

        # Any is also the bottom type - Any is a subtype of everything
        if self.raw is Any:
            return True

        # handle union for self
        if self.is_union:
            return all(a.is_subtype(other_ann) for a in self.arg_annotations)

        # handle union for other
        if other_ann.is_union:
            return any(self.is_subtype(a) for a in other_ann.arg_annotations)

        # handle literal for self
        if self.is_literal:
            return all(other_ann.check_instance(value) for value in self.args)

        # handle literal for other: non-literal can never be a "subclass" of literal
        if other_ann.is_literal:
            return False

        # handle callables
        if self.is_callable or other_ann.is_callable:
            if not self.is_callable and other_ann.is_callable:
                # callable type (e.g., int, str) being compared to Callable
                return self._is_subtype_callable_type(other_ann)
            return self._is_subtype_callable(other_ann)

        # check concrete type relationship
        # - for ABCs/protocols, issubclass may succeed even if not in MRO
        is_concrete_subtype = robust_issubclass(
            self.concrete_type, other_ann.concrete_type
        )

        if not is_concrete_subtype:
            return False

        # concrete type matches, now check type parameters
        if not other_ann.args:
            return True

        # other has type parameters, need to extract and compare
        my_args = self._extract_my_args(other_ann.concrete_type)
        other_args = other_ann.arg_annotations

        # pad missing args in my_arg_annotations, assumed to be Any
        if len(my_args) < len(other_args):
            my_args = list(my_args) + [ANY] * (len(other_args) - len(my_args))

        # recurse into args
        for my_arg, other_arg in zip(my_args, other_args):
            if not my_arg.is_subtype(other_arg):
                return False

        return True

    def check_instance(self, obj: Any, /, *, recurse: bool = True) -> bool:
        """
        Check if object is an instance of this annotation; roughly equivalent to
        `isinstance(obj, annotation)`.

        Examples:

        - `Annotation(Any).check_instance(1)` returns `True`
        - `Annotation(list[int]).check_instance([1, 2, 3])` returns `True`
        - `Annotation(list[int]).check_instance([1, 2, "3"])` returns `False`
        """
        if self.is_literal:
            return any(obj == value for value in self.args)

        if self.is_union:
            return any(
                a.check_instance(obj, recurse=recurse) for a in self.arg_annotations
            )

        if self.is_callable:
            return self._check_callable(obj)

        if not isinstance(obj, self.concrete_type):
            return False

        if recurse and issubclass(self.concrete_type, (list, tuple, set, dict)):
            return self._check_collection(obj)

        # concrete type matches and is not a collection (or we're not recursing)
        return True

    @classmethod
    def _normalize(cls, obj: Annotation | Any) -> Annotation:
        return obj if isinstance(obj, Annotation) else Annotation(obj)

    def _is_subtype_callable(self, other: Annotation) -> bool:
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
            return self.return_annotation.is_subtype(other.return_annotation)

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
            if not other_param.is_subtype(my_param):
                return False

        return self.return_annotation.is_subtype(other.return_annotation)

    def _is_subtype_callable_type(self, other: Annotation) -> bool:
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

        # with ... parameters we accept any parameters, so contravariance always
        # satisfied
        return return_ann.is_subtype(other.return_annotation)

    def _check_callable(self, obj: Any) -> bool:
        """
        Check if object matches this callable annotation.
        """
        if not callable(obj):
            return False

        # if Callable[..., ReturnType], just check it's callable
        if self.param_annotations is None:
            return True

        # try to validate parameter count
        try:
            sig = inspect.signature(obj)
            # count positional and positional-or-keyword parameters
            param_count = sum(
                1
                for p in sig.parameters.values()
                if p.kind
                in (
                    Parameter.POSITIONAL_ONLY,
                    Parameter.POSITIONAL_OR_KEYWORD,
                )
            )

            return param_count == len(self.param_annotations)
        except (ValueError, TypeError):
            # can't get signature (e.g., built-in functions), assume it's fine
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
        other_type = list if isinstance(obj, list) else set
        my_args = self._extract_my_args(other_type)
        assert len(my_args) in {0, 1}
        arg = my_args[0] if len(my_args) else ANY
        if arg == ANY:
            return True
        return all(arg.check_instance(o) for o in obj)

    def _check_tuple(self, obj: tuple[Any]) -> bool:
        args = extract_tuple_args(self)
        if isinstance(args, tuple):
            # fixed-length tuple
            if len(args) != len(obj):
                return False
            return all(a.check_instance(o) for a, o in zip(args, obj))
        else:
            # variadic tuple
            if args == ANY:
                return True
            return all(args.check_instance(o) for o in obj)

    def _check_dict(self, obj: dict[Any, Any]) -> bool:
        my_args = self._extract_my_args(dict)
        assert len(my_args) in {0, 2}
        key_ann, value_ann = my_args if len(my_args) == 2 else (ANY, ANY)
        if (key_ann, value_ann) == (ANY, ANY):
            return True
        return all(
            key_ann.check_instance(k) and value_ann.check_instance(v)
            for k, v in obj.items()
        )

    def _extract_my_args(self, other: type) -> tuple[Annotation, ...]:
        """
        Get my args as passed to the other class.
        """
        try:
            # extract the type args that self passes to other's concrete type
            # - use extract_args() to handle ABCs/protocols not in MRO
            my_args = normalize_args(extract_args(self.concrete_type, other))
        except TypeError:
            # base class not found in hierarchy, fall back to self's args
            my_args = self.args
        else:
            # if extract_args returns empty but self has args, use self's args
            # (this happens when comparing e.g. list[int] to list[str])
            if not my_args:
                return self.arg_annotations
        return tuple(Annotation(a) for a in my_args)


def is_subtype(annotation: Annotation | Any, other: Annotation | Any, /) -> bool:
    """
    Check whether an annotation is a subtype of another annotation.

    Accommodates generic types and fully resolves type aliases, unions, and
    `Annotated`.

    Example:

    ```python
    assert is_subtype(list[int], list[int | str])
    ```
    """
    return Annotation._normalize(annotation).is_subtype(other)


def is_instance(obj: Any, annotation: Annotation | Any, /) -> bool:
    """
    Check whether an object is an "instance" of an annotation.

    Accommodates generic types and fully resolves type aliases, unions, and
    `Annotated`.

    Example:

    ```python
    assert is_instance([1, 2, "3"], list[int | str])
    ```
    """
    return Annotation._normalize(annotation).check_instance(obj)


def is_union(annotation: Any, /) -> bool:
    """
    Check whether annotation is a union, accommodating both `int | str`
    and `Union[int, str]`.
    """
    return isinstance(annotation, UnionType) or get_origin(annotation) is Union


def unwrap_alias(annotation: Any, /) -> Any:
    """
    If annotation is a `TypeAlias`, extract the corresponding definition.
    """
    if isinstance(annotation, TypeAliasType):
        return annotation.__value__
    elif isinstance(annotation, GenericAlias):
        # might have e.g.:
        # type MyType[T] = list[T]
        # unwrap_alias(MyType[T])
        origin = get_origin(annotation)
        if isinstance(origin, TypeAliasType):
            # have e.g. MyType[T], return list[T]
            return origin.__value__
    return annotation


def split_annotated(annotation: Any, /) -> tuple[Any, tuple[Any, ...]]:
    """
    If annotation is an `Annotated`, split it into the wrapped annotation and extras.
    """
    if get_origin(annotation) is Annotated:
        args = get_args(annotation)
        assert len(args)
        return args[0], tuple(args[1:])
    return annotation, ()


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

    if concrete_type is Literal:
        return cast(type, LiteralType)

    if concrete_type is Any:
        return object

    if isinstance(concrete_type, TypeVar):
        concrete_type = concrete_type.__bound__

    # convert singletons to respective type so isinstance() works as expected
    singleton_map = {None: NoneType, Ellipsis: EllipsisType, Union: UnionType}
    concrete_type = singleton_map.get(concrete_type, concrete_type)

    assert isinstance(
        concrete_type, type
    ), f"Not a type: '{concrete_type}' (from annotation '{annotation}' normalized to '{annotation_}')"

    return concrete_type


def extract_tuple_args(
    annotation: Annotation, /
) -> Annotation | tuple[Annotation, ...]:
    """
    Extract args from the tuple.

    - Returns `Annotation` if the tuple is variadic (e.g. `tuple[int, ...]`)
    - Returns a tuple of `Annotation` if the tuple is fixed-length
    (e.g. tuple[int, str])
    """
    assert issubclass(annotation.concrete_type, tuple)

    if annotation.concrete_type is tuple:
        args = annotation.arg_annotations
    else:
        # subclass of tuple
        raw_args = extract_args(annotation.concrete_type, tuple)
        args = tuple(Annotation(a) for a in raw_args)

    if len(args) == 0:
        # assume tuple[Any, ...]
        return ANY

    if args[-1].raw is ...:
        # variadic tuple like tuple[int, ...]
        assert len(args) == 2
        return args[0]
    else:
        # fixed-length tuple like tuple[int, str]
        return args


def _recurse_union(annotation: Any, /, *, preserve_extras: bool) -> list[Any]:
    args: list[Any] = []
    annotation_ = normalize_annotation(annotation, preserve_extras=preserve_extras)

    if is_union(annotation_):
        for a in get_args(annotation_):
            args += _recurse_union(a, preserve_extras=preserve_extras)
    else:
        args.append(annotation_)

    return args


ANY = Annotation(Any)
"""
Annotation encapsulating `Any`.
"""

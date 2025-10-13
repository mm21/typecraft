"""
Utilities to recursively convert and validate objects.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any, Callable, Generator, Literal, Union, cast, overload

from .inspecting import Annotation, flatten_union

__all__ = [
    "ConvertFuncType",
    "ConvertContext",
    "Converter",
    "validate",
    "normalize_to_list",
]


type ConvertFuncType[T] = Callable[[Any], T] | Callable[
    [Any, Annotation, ConvertContext], T
]
"""
Function which converts the given object. Can optionally take the annotation and
context, generally used to propagate to nested objects (e.g. elements of custom
collections).
"""

type VarianceType = Literal["contravariant", "invariant"]
"""
Variance supported by a converter.
"""

type ValueCollectionType = list | tuple | set | frozenset | range | Generator
"""
Types convertible to lists, tuples, and sets; collections which contain values
rather than key-value mappings.
"""

type CollectionType = ValueCollectionType | Mapping
"""
Types convertible to collection types.
"""

VALUE_COLLECTION_TYPES = flatten_union(ValueCollectionType)
COLLECTION_TYPES = flatten_union(CollectionType)


class ConvertContext:
    """
    Encapsulates conversion parameters, propagated throughout the conversion process.
    """

    # TODO: converter registry instead of tuple
    __converters: tuple[Converter, ...]
    __lenient: bool = False

    # TODO: always: perform conversion even if type already matches target (for
    # serialization)

    def __init__(self, *converters: Converter, lenient: bool = False):
        self.__converters = converters
        self.__lenient = lenient

    def __repr__(self) -> str:
        return (
            f"ConvertContext(converters={self.__converters}, lenient={self.__lenient})"
        )

    def validate(self, obj: Any, annotation_info: Annotation) -> Any:
        return _dispatch_validation(obj, annotation_info, self)

    @property
    def converters(self) -> tuple[Converter, ...]:
        return self.__converters

    @property
    def lenient(self) -> bool:
        return self.__lenient


class Converter[T = Any]:
    """
    Encapsulates type conversion parameters from a source annotation (which may be
    a union) to a target annotation.
    """

    __source_annotation: Annotation
    """
    Annotation specifying type to convert from.
    """

    __target_annotation: Annotation
    """
    Annotation specifying type to convert to.
    """

    __func: ConvertFuncType[Any] | None
    """
    Callable returning an instance of target type. Must take exactly one positional
    argument of one of the type(s) given in `from_types`. May be the target type itself
    if its constructor takes exactly one positional argument.
    """

    __variance: VarianceType

    @overload
    def __init__(
        self,
        source_annotation: Any,
        target_annotation: type[T],
        /,
        *,
        func: ConvertFuncType[T] | None = None,
        variance: VarianceType = "contravariant",
    ): ...

    @overload
    def __init__(
        self,
        source_annotation: Any,
        target_annotation: Any = Any,
        /,
        *,
        func: ConvertFuncType[Any] | None = None,
        variance: VarianceType = "contravariant",
    ): ...

    def __init__(
        self,
        source_annotation: Any,
        target_annotation: Any = Any,
        func: ConvertFuncType[Any] | None = None,
        variance: VarianceType = "contravariant",
    ):
        self.__source_annotation = Annotation(source_annotation)
        self.__target_annotation = Annotation(target_annotation)
        self.__func = func
        self.__variance = variance

    def __repr__(self) -> str:
        return f"Converter(source={self.__source_annotation}, target={self.__target_annotation}, func={self.__func}), variance={self.__variance}"

    @property
    def target_annotation(self) -> Annotation:
        return self.__target_annotation

    @property
    def source_annotation(self) -> Annotation:
        return self.__source_annotation

    def convert(
        self,
        obj: Any,
        target_annotation: Annotation,
        context: ConvertContext | None = None,
        /,
    ) -> T:
        """
        Convert object or raise `ValueError`.

        `target_annotation` is required because some converters may inspect it to
        recurse into items of collections. For example, a converter to MyList[T]
        would invoke conversion to type T on each item.
        """
        if not self.can_convert(obj, target_annotation):
            raise ValueError(
                f"Object '{obj}' ({type(obj)}) cannot be converted using {self}"
            )

        context_ = context or ConvertContext(self)

        try:
            if self.__func:
                # provided convert function
                sig = inspect.signature(self.__func)
                if len(sig.parameters) == 1:
                    func = cast(Callable[[Any], Any], self.__func)
                    new_obj = func(obj)
                else:
                    func = cast(
                        Callable[[Any, Annotation, ConvertContext], Any], self.__func
                    )
                    new_obj = func(obj, target_annotation, context_)
            else:
                # direct object construction
                concrete_type = cast(
                    Callable[[Any], T], self.__target_annotation.concrete_type
                )
                new_obj = concrete_type(obj)
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"Converter {self} failed to convert {obj} ({type(obj)}): {e}"
            ) from None

        if not isinstance(new_obj, self.__target_annotation.concrete_type):
            raise ValueError(
                f"Converter {self} failed to convert {obj} ({type(obj)}), got {new_obj} ({type(new_obj)})"
            )

        return new_obj

    @overload
    def can_convert(self, obj: Any, target_annotation: Annotation, /) -> bool: ...

    @overload
    def can_convert(self, obj: Any, target_annotation: Any, /) -> bool: ...

    def can_convert(self, obj: Any, target_annotation: Any, /) -> bool:
        """
        Check if this converter can convert the given object to the given annotation.
        """
        target_annotation_ = (
            target_annotation
            if isinstance(target_annotation, Annotation)
            else Annotation(target_annotation)
        )

        if self.__variance == "invariant":
            # exact match only
            if not target_annotation_ == self.__target_annotation:
                return False
        else:
            # contravariant (default): annotation must be a subclass of
            # self.__target_annotation
            # - for example, a converter configured with target BaseModel can also
            # convert UserModel
            if not target_annotation_.is_subclass(self.__target_annotation):
                return False

        # check source
        return self.__source_annotation.is_type(obj)


# TODO: take converter registry instead of tuple
@overload
def validate[T](
    obj: Any,
    target_type: type[T],
    /,
    *converters: Converter[T],
    lenient: bool = False,
) -> T: ...


@overload
def validate(
    obj: Any,
    target_type: Any,
    /,
    *converters: Converter[Any],
    lenient: bool = False,
) -> Any: ...


def validate(
    obj: Any,
    target_type: Any,
    /,
    *converters: Converter[Any],
    lenient: bool = False,
) -> Any:
    """
    Recursively validate object, converting to the target type if applicable.

    Handles nested parameterized types like list[list[int]] by recursively
    applying validation and conversion at each level.
    """
    annotation_info = Annotation(target_type)
    context = ConvertContext(*converters, lenient=lenient)
    return _dispatch_validation(obj, annotation_info, context)


def normalize_to_list[T](
    obj_or_objs: Any,
    target_type: type[T],
    /,
    *converters: Converter[T],
    lenient: bool = False,
) -> list[T]:
    """
    Validate object(s) and normalize to a list of the target type.

    Only built-in collection types and generators are expanded.
    Custom types (even if iterable) are treated as single objects.
    """
    # normalize to a collection of objects
    if isinstance(obj_or_objs, VALUE_COLLECTION_TYPES):
        objs = obj_or_objs
    else:
        objs = [obj_or_objs]

    # validate each object and place in a new list
    return [validate(o, target_type, *converters, lenient=lenient) for o in objs]


def _dispatch_validation(
    obj: Any,
    annotation_info: Annotation,
    context: ConvertContext,
) -> Any:

    # handle union type
    if annotation_info.is_union:
        return _validate_union(obj, annotation_info, context)

    # if object does not satisfy annotation, attempt conversion
    # - converters (custom and lenient conversions) are assumed to always recurse if
    # applicable
    if not _check_valid(obj, annotation_info):
        return _convert(obj, annotation_info, context)

    # if type is a builtin collection, recurse
    if issubclass(annotation_info.concrete_type, (list, tuple, set, dict)):
        assert isinstance(obj, COLLECTION_TYPES)
        return _validate_collection(obj, annotation_info, context)

    # have the expected type and it's not a collection
    return obj


def _validate_union(
    obj: Any, annotation_info: Annotation, context: ConvertContext
) -> Any:
    """
    Validate constituent types of union.
    """
    for arg in annotation_info.arg_annotations:
        try:
            return _dispatch_validation(obj, arg, context)
        except (ValueError, TypeError):
            continue
    raise ValueError(
        f"Object '{obj}' ({type(obj)}) could not be converted to any member of union {annotation_info}"
    )


def _check_valid(obj: Any, annotation_info: Annotation) -> bool:
    """
    Check if object satisfies the annotation.
    """
    if annotation_info.is_literal:
        return obj in annotation_info.args
    else:
        return isinstance(obj, annotation_info.concrete_type)


def _validate_collection(
    obj: CollectionType,
    annotation_info: Annotation,
    context: ConvertContext,
) -> Any:
    """
    Validate collection of objects.
    """

    assert len(
        annotation_info.arg_annotations
    ), f"Collection has no type parameter: {obj} ({annotation_info})"

    type_ = annotation_info.concrete_type

    # handle conversion from mappings
    if issubclass(type_, dict):
        assert isinstance(obj, Mapping)
        return _validate_dict(obj, annotation_info, context)

    # handle conversion from value collections
    assert not isinstance(obj, Mapping)
    if issubclass(type_, list):
        return _validate_list(obj, annotation_info, context)
    elif issubclass(type_, tuple):
        return _validate_tuple(obj, annotation_info, context)
    else:
        assert issubclass(type_, set)
        return _validate_set(obj, annotation_info, context)


def _validate_list(
    obj: ValueCollectionType,
    annotation_info: Annotation,
    context: ConvertContext,
) -> list[Any]:
    type_ = annotation_info.concrete_type
    assert issubclass(type_, list)
    assert len(annotation_info.arg_annotations) == 1

    arg = annotation_info.arg_annotations[0]
    validated_objs = [context.validate(o, arg) for o in obj]

    if isinstance(obj, type_) and all(o is n for o, n in zip(obj, validated_objs)):
        return obj
    elif type_ is list:
        return validated_objs
    return type_(validated_objs)


def _validate_tuple(
    obj: ValueCollectionType,
    annotation_info: Annotation,
    context: ConvertContext,
) -> tuple[Any]:
    type_ = annotation_info.concrete_type
    assert issubclass(type_, tuple)

    if annotation_info.arg_annotations[-1].annotation is not ...:
        # fixed-length tuple like tuple[int, str, float]
        assert not isinstance(
            obj, set
        ), f"Can't convert from set to fixed-length tuple as items would be in random order: {obj} ({annotation_info})"

        # ensure object is sized
        sized_obj = list(obj) if isinstance(obj, (range, Generator)) else obj

        if len(sized_obj) != len(annotation_info.arg_annotations):
            raise ValueError(
                f"Tuple length mismatch: expected {len(annotation_info.arg_annotations)}, got {len(sized_obj)}: {sized_obj} ({annotation_info})"
            )
        validated_objs = tuple(
            context.validate(o, arg)
            for o, arg in zip(sized_obj, annotation_info.arg_annotations)
        )
    else:
        # homogeneous tuple like tuple[int, ...]
        assert len(annotation_info.arg_annotations) == 2
        arg = annotation_info.arg_annotations[0]
        validated_objs = tuple(context.validate(o, arg) for o in obj)

    if isinstance(obj, type_) and all(o is n for o, n in zip(obj, validated_objs)):
        return obj
    elif type_ is tuple:
        return validated_objs
    return type_(validated_objs)


def _validate_set(
    obj: ValueCollectionType,
    annotation_info: Annotation,
    context: ConvertContext,
) -> set[Any]:
    type_ = annotation_info.concrete_type
    assert issubclass(type_, set)
    assert len(annotation_info.arg_annotations) == 1

    arg = annotation_info.arg_annotations[0]
    validated_objs = {context.validate(o, arg) for o in obj}

    if isinstance(obj, type_):
        obj_ids = {id(o) for o in obj}
        if all(id(n) in obj_ids for n in validated_objs):
            return obj
    if type_ is set:
        return validated_objs
    return type_(validated_objs)


def _validate_dict(
    obj: Mapping,
    annotation_info: Annotation,
    context: ConvertContext,
) -> dict:
    type_ = annotation_info.concrete_type
    assert issubclass(type_, dict)
    assert len(annotation_info.arg_annotations) == 2
    key_type, value_type = annotation_info.arg_annotations

    validated_objs = {
        context.validate(k, key_type): context.validate(v, value_type)
        for k, v in obj.items()
    }

    if isinstance(obj, type_) and all(
        k_o is k_n and obj[k_o] is validated_objs[k_n]
        for k_o, k_n in zip(obj, validated_objs)
    ):
        return obj
    elif type_ is dict:
        return validated_objs
    return type_(**validated_objs)


def _convert(obj: Any, target_annotation: Annotation, context: ConvertContext) -> Any:
    """
    Convert object by invoking converters and built-in handling, raising `ValueError`
    if it could not be converted.
    """
    # TODO: wrap in ConverterRegistry

    # try user-provided converters
    if converter := _find_converter(obj, target_annotation, context.converters):
        return converter.convert(obj, target_annotation, context)

    # if lenient, keep trying
    if context.lenient:
        # built-in converters
        if converter := _find_converter(obj, target_annotation, BUILTIN_CONVERTERS):
            return converter.convert(obj, target_annotation, context)

        # direct object construction
        return target_annotation.concrete_type(obj)

    raise ValueError(
        f"Object '{obj}' ({type(obj)}) could not be converted to {target_annotation}"
    )


def _find_converter(
    obj: Any, target_annotation: Annotation, converters: tuple[Converter, ...]
) -> Converter | None:
    """
    Find the first converter that can handle the given object to target type conversion.
    """
    for converter in converters:
        if converter.can_convert(obj, target_annotation):
            return converter
    return None


BUILTIN_CONVERTERS = (
    Converter(Union[VALUE_COLLECTION_TYPES], list, func=_validate_list),
    Converter(Union[VALUE_COLLECTION_TYPES], tuple, func=_validate_tuple),
    Converter(Union[VALUE_COLLECTION_TYPES], set, func=_validate_set),
    Converter(Mapping, dict, func=_validate_dict),
)

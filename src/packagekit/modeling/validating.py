"""
Utilities to validate and convert objects recursively.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import UnionType
from typing import Any, Callable, Generator, cast, overload

from .typing_utils import AnnotationInfo, RawAnnotationType

__all__ = [
    "ConverterFuncType",
    "ConversionContext",
    "Converter",
    "validate_obj",
    "validate_objs",
]


type ConverterFuncType[T] = Callable[[Any, AnnotationInfo, ConversionContext], T]
"""
Function which converts the given object.
"""

type ValueCollectionType = list[Any] | tuple[Any] | set[Any] | frozenset[
    Any
] | range | Generator
"""
Types convertible to lists, tuples, and sets; collections which contain values
rather than key-value mappings.
"""

type CollectionType = ValueCollectionType | Mapping
"""
Types convertible to collection types.
"""

VALUE_COLLECTION_TYPES = (
    list,
    tuple,
    set,
    frozenset,
    range,
    Generator,
)

COLLECTION_TYPES = (*VALUE_COLLECTION_TYPES, Mapping)


class ConversionContext:
    """
    Encapsulates conversion parameters, propagated throughout the conversion process.
    """

    __converters: tuple[Converter, ...]
    __lenient: bool = False

    def __init__(self, *converters: Converter, lenient: bool):
        self.__converters = converters
        self.__lenient = lenient

    def __repr__(self) -> str:
        return f"ConversionContext(converters={self.__converters}, lenient={self.__lenient})"

    def validate_obj(self, obj: Any, annotation_info: AnnotationInfo) -> Any:
        return _validate_obj(obj, annotation_info, self)

    @property
    def converters(self) -> tuple[Converter, ...]:
        return self.__converters

    @property
    def lenient(self) -> bool:
        return self.__lenient


class Converter[T]:
    """
    Encapsulates type conversion parameters from one or more types to a target type.
    """

    __target_type: type[T]
    """
    Concrete type to convert to.
    """

    __source_types: tuple[type[Any], ...]
    """
    Concrete type(s) to convert from. An empty tuple means factory can accept any type.
    """

    __func: ConverterFuncType[T] | None
    """
    Callable returning an instance of target type. Must take exactly one positional
    argument of one of the type(s) given in `from_types`. May be the target type itself
    if its constructor takes exactly one positional argument.
    """

    def __init__(
        self,
        target_type: type[T],
        source_types: tuple[type[Any], ...] = (),
        func: ConverterFuncType[T] | None = None,
    ):
        self.__target_type = target_type
        self.__source_types = source_types
        self.__func = func

    def __repr__(self) -> str:
        return f"Converter(target_type={self.__target_type}, source_types={self.__source_types}, func={self.__func})"

    @property
    def target_type(self) -> type[T]:
        return self.__target_type

    @property
    def source_types(self) -> tuple[type[Any], ...]:
        return self.__source_types

    def convert(
        self,
        obj: Any,
        annotation_info: AnnotationInfo,
        conversion_context: ConversionContext,
        /,
    ) -> T:
        """
        Convert object or raise `ValueError`.
        """
        if not self.can_convert(obj, self.__target_type):
            raise ValueError(
                f"Object '{obj}' ({type(obj)}) cannot be converted using {self}"
            )

        try:
            if self.__func:
                new_obj = self.__func(obj, annotation_info, conversion_context)
            else:
                new_obj = cast(Callable[[Any], T], self.__target_type)(obj)
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"Converter {self} failed to convert {obj} ({type(obj)}): {e}"
            ) from None

        if not isinstance(new_obj, self.__target_type):
            raise ValueError(
                f"Converter {self} failed to convert {obj} ({type(obj)}), got {new_obj} ({type(new_obj)})"
            )

        return new_obj

    def can_convert(self, obj: Any, target_type: type[Any], /) -> bool:
        """
        Check if this converter can convert the given object.
        """
        target_match = issubclass(target_type, self.__target_type)
        source_match = len(self.__source_types) == 0 or isinstance(
            obj, self.__source_types
        )
        return target_match and source_match


@overload
def validate_obj[T](
    obj: Any,
    target_type: type[T],
    /,
    *converters: Converter[T],
    lenient: bool = False,
) -> T: ...


@overload
def validate_obj(
    obj: Any,
    target_type: RawAnnotationType,
    /,
    *converters: Converter[Any],
    lenient: bool = False,
) -> Any: ...


def validate_obj(
    obj: Any,
    target_type: RawAnnotationType,
    /,
    *converters: Converter[Any],
    lenient: bool = False,
) -> Any:
    """
    Recursively normalize object to the target type, converting if applicable.

    Handles nested parameterized types like list[list[int]] by recursively
    applying converters at each level.
    """
    annotation_info = AnnotationInfo(target_type)
    conversion_context = ConversionContext(*converters, lenient=lenient)
    return _validate_obj(obj, annotation_info, conversion_context)


def validate_objs[T](
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

    # normalize each object and place in a new list
    return [validate_obj(o, target_type, *converters, lenient=lenient) for o in objs]


def _validate_obj(
    obj: Any,
    annotation_info: AnnotationInfo,
    conversion_context: ConversionContext,
) -> Any:

    # handle union types by trying each constituent type
    if isinstance(annotation_info.annotation, UnionType):
        for arg in annotation_info.args:
            try:
                return _validate_obj(obj, arg, conversion_context)
            except (ValueError, TypeError):
                continue
        raise ValueError(
            f"Object {obj} ({type(obj)}) could not be converted to any member of union {annotation_info}"
        )

    # if we don't have the expected type, attempt conversion
    # - converters (custom and lenient conversions) are assumed to always recurse if
    # applicable
    if not isinstance(obj, annotation_info.concrete_type):
        return _convert_obj(obj, annotation_info, conversion_context)

    # if type is a builtin collection, recurse
    if issubclass(annotation_info.concrete_type, (list, tuple, set, dict)):
        assert isinstance(obj, COLLECTION_TYPES)
        return _validate_collection(obj, annotation_info, conversion_context)

    # have the expected type and it's not a collection
    return obj


def _validate_collection(
    obj: CollectionType,
    annotation_info: AnnotationInfo,
    conversion_context: ConversionContext,
) -> Any:
    """
    Normalize collection of objects.
    """

    assert len(
        annotation_info.args
    ), f"Collection has no type parameter: {obj} ({annotation_info})"

    # handle conversion from mappings
    if issubclass(annotation_info.concrete_type, dict):
        assert isinstance(obj, Mapping)
        return _validate_dict(obj, annotation_info, conversion_context)

    # handle conversion from value collections
    assert not isinstance(obj, Mapping)
    if issubclass(annotation_info.concrete_type, list):
        return _validate_list(obj, annotation_info, conversion_context)
    elif issubclass(annotation_info.concrete_type, tuple):
        return _validate_tuple(obj, annotation_info, conversion_context)
    else:
        assert issubclass(annotation_info.concrete_type, set)
        return _validate_set(obj, annotation_info, conversion_context)


def _validate_list(
    obj: ValueCollectionType,
    annotation_info: AnnotationInfo,
    conversion_context: ConversionContext,
) -> list[Any]:
    assert issubclass(annotation_info.concrete_type, list)
    assert len(annotation_info.args) == 1

    arg = annotation_info.args[0]
    normalized_objs = [conversion_context.validate_obj(o, arg) for o in obj]

    if isinstance(obj, annotation_info.concrete_type) and obj == normalized_objs:
        return obj
    else:
        return normalized_objs


def _validate_tuple(
    obj: ValueCollectionType,
    annotation_info: AnnotationInfo,
    conversion_context: ConversionContext,
) -> tuple[Any]:
    assert issubclass(annotation_info.concrete_type, tuple)

    # fixed-length tuple like tuple[int, str, float]
    if annotation_info.args[-1].annotation is not ...:
        assert not isinstance(
            obj, set
        ), f"Can't convert from set to fixed-length tuple as items would be in random order: {obj} ({annotation_info})"

        # ensure object is sized
        sized_obj = list(obj) if isinstance(obj, (range, Generator)) else obj

        if len(sized_obj) != len(annotation_info.args):
            raise ValueError(
                f"Tuple length mismatch: expected {len(annotation_info.args)}, got {len(sized_obj)}: {sized_obj} ({annotation_info})"
            )
        normalized_objs = tuple(
            conversion_context.validate_obj(o, arg)
            for o, arg in zip(sized_obj, annotation_info.args)
        )
    else:
        # homogeneous tuple like tuple[int, ...]
        assert len(annotation_info.args) == 2
        arg = annotation_info.args[0]
        normalized_objs = tuple(conversion_context.validate_obj(o, arg) for o in obj)

    if isinstance(obj, tuple) and obj == normalized_objs:
        return obj
    else:
        return normalized_objs


def _validate_set(
    obj: ValueCollectionType,
    annotation_info: AnnotationInfo,
    conversion_context: ConversionContext,
) -> set[Any]:
    assert issubclass(annotation_info.concrete_type, set)
    assert len(annotation_info.args) == 1

    arg = annotation_info.args[0]
    normalized_objs = {conversion_context.validate_obj(o, arg) for o in obj}

    if isinstance(obj, set) and obj == normalized_objs:
        return obj
    else:
        return normalized_objs


def _validate_dict(
    obj: Mapping,
    annotation_info: AnnotationInfo,
    conversion_context: ConversionContext,
) -> dict:
    assert issubclass(annotation_info.concrete_type, dict)
    assert len(annotation_info.args) == 2
    key_type, value_type = annotation_info.args

    normalized_objs = {
        conversion_context.validate_obj(k, key_type): conversion_context.validate_obj(
            v, value_type
        )
        for k, v in obj.items()
    }

    if isinstance(obj, dict) and obj == normalized_objs:
        return obj
    else:
        return normalized_objs


def _convert_obj(
    obj: Any, annotation_info: AnnotationInfo, conversion_context: ConversionContext
) -> Any:
    """
    Convert object by invoking converters and built-in handling, raising `ValueError`
    if it could not be converted.
    """
    # try user-provided converters
    if converter := _find_converter(
        obj, annotation_info.concrete_type, conversion_context.converters
    ):
        return converter.convert(obj, annotation_info, conversion_context)

    # if lenient, keep trying
    if conversion_context.lenient:
        # built-in converters
        if converter := _find_converter(
            obj, annotation_info.concrete_type, BUILTIN_CONVERTERS
        ):
            return converter.convert(obj, annotation_info, conversion_context)

        # direct object construction
        return annotation_info.concrete_type(obj)

    raise ValueError(
        f"Object '{obj}' ({type(obj)}) could not be converted to {annotation_info.concrete_type} ({annotation_info})"
    )


def _find_converter(
    obj: Any, target_type: type[Any], converters: tuple[Converter, ...]
) -> Converter | None:
    """
    Find the first converter that can handle the given object to target type conversion.
    """
    for converter in converters:
        if converter.can_convert(obj, target_type):
            return converter
    return None


BUILTIN_CONVERTERS = (
    Converter(list, VALUE_COLLECTION_TYPES, _validate_list),
    Converter(tuple, VALUE_COLLECTION_TYPES, _validate_tuple),
    Converter(set, VALUE_COLLECTION_TYPES, _validate_set),
    Converter(dict, (Mapping,), _validate_dict),
)

"""
Utilities to recursively convert and validate objects.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable, Generator, cast, overload

from .inspecting import Annotation, flatten_union

__all__ = [
    "ConverterFuncType",
    "ConversionContext",
    "Converter",
    "validate_obj",
    "validate_objs",
]


type ConverterFuncType[T] = Callable[[Any, Annotation, ConversionContext], T]
"""
Function which converts the given object.
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

print(f"--- VALUE_COLLECTION_TYPES: {VALUE_COLLECTION_TYPES}")
print(f"--- COLLECTION_TYPES: {COLLECTION_TYPES}")


class ConversionContext:
    """
    Encapsulates conversion parameters, propagated throughout the conversion process.
    """

    __converters: tuple[Converter, ...]
    __lenient: bool = False

    def __init__(self, *converters: Converter, lenient: bool = False):
        self.__converters = converters
        self.__lenient = lenient

    def __repr__(self) -> str:
        return f"ValidationContext(converters={self.__converters}, lenient={self.__lenient})"

    def validate_obj(self, obj: Any, annotation_info: Annotation) -> Any:
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

    # TODO: just have annotation info, not type

    __target_annotation_info: Annotation

    __target_type: type[T]
    """
    Concrete type to convert to.
    """

    __source_annotation_info: tuple[Annotation, ...]

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

    @overload
    def __init__(
        self,
        target_type: type[T],
        source_types: tuple[type[Any], ...] = (),
        func: ConverterFuncType[T] | None = None,
    ): ...

    @overload
    def __init__(
        self,
        target_type: Any,
        source_types: tuple[Any, ...] = (),
        func: ConverterFuncType[T] | None = None,
    ): ...

    def __init__(
        self,
        target_type: type[T],
        source_types: tuple[type[Any], ...] = (),
        func: ConverterFuncType[T] | None = None,
    ):
        self.__target_annotation_info = Annotation(target_type)
        self.__target_type = target_type
        self.__source_annotation_info = tuple(Annotation(s) for s in source_types)
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
        annotation_info: Annotation,
        context: ConversionContext | None = None,
        /,
    ) -> T:
        """
        Convert object or raise `ValueError`.
        """
        if not self.can_convert(obj, self.__target_type):
            raise ValueError(
                f"Object '{obj}' ({type(obj)}) cannot be converted using {self}"
            )

        context_ = context or ConversionContext()

        try:
            if self.__func:
                new_obj = self.__func(obj, annotation_info, context_)
            else:
                new_obj = cast(Callable[[Any], T], self.__target_type)(obj)
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"Converter {self} failed to convert {obj} ({type(obj)}): {e}"
            ) from None

        if not isinstance(new_obj, self.__target_annotation_info.concrete_type):
            raise ValueError(
                f"Converter {self} failed to convert {obj} ({type(obj)}), got {new_obj} ({type(new_obj)})"
            )

        return new_obj

    # TODO: take target_type as AnnotationInfo
    @overload
    def can_convert(self, obj: Any, target_type: type[Any], /) -> bool: ...

    @overload
    def can_convert(self, obj: Any, target_type: Any, /) -> bool: ...

    def can_convert(self, obj: Any, target_type: type[Any], /) -> bool:
        """
        Check if this converter can convert the given object.
        """
        target_annotation_info = Annotation(target_type)

        # check target
        if not target_annotation_info.is_subclass(self.__target_annotation_info):
            return False

        # check source(s)
        return len(self.__source_types) == 0 or any(
            isinstance(obj, s.concrete_type) for s in self.__source_annotation_info
        )


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
    target_type: Any,
    /,
    *converters: Converter[Any],
    lenient: bool = False,
) -> Any: ...


def validate_obj(
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
    context = ConversionContext(*converters, lenient=lenient)
    return _validate_obj(obj, annotation_info, context)


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

    # validate each object and place in a new list
    return [validate_obj(o, target_type, *converters, lenient=lenient) for o in objs]


def _validate_obj(
    obj: Any,
    annotation_info: Annotation,
    context: ConversionContext,
) -> Any:

    # handle union type
    if annotation_info.is_union:
        return _validate_union(obj, annotation_info, context)

    # if object does not satisfy annotation, attempt conversion
    # - converters (custom and lenient conversions) are assumed to always recurse if
    # applicable
    if not _check_obj(obj, annotation_info):
        return _convert_obj(obj, annotation_info, context)

    # if type is a builtin collection, recurse
    if issubclass(annotation_info.concrete_type, (list, tuple, set, dict)):
        assert isinstance(obj, COLLECTION_TYPES)
        return _validate_collection(obj, annotation_info, context)

    # have the expected type and it's not a collection
    return obj


def _check_obj(obj: Any, annotation_info: Annotation) -> bool:
    """
    Check if object satisfies the annotation.
    """
    if annotation_info.is_literal:
        return obj in annotation_info.args
    else:
        return isinstance(obj, annotation_info.concrete_type)


def _validate_union(
    obj: Any, annotation_info: Annotation, context: ConversionContext
) -> Any:
    """
    Validate constituent types of union.
    """
    for arg in annotation_info.arg_annotations:
        try:
            return _validate_obj(obj, arg, context)
        except (ValueError, TypeError):
            continue
    raise ValueError(
        f"Object '{obj}' ({type(obj)}) could not be converted to any member of union {annotation_info}"
    )


def _validate_collection(
    obj: CollectionType,
    annotation_info: Annotation,
    context: ConversionContext,
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
    context: ConversionContext,
) -> list[Any]:
    type_ = annotation_info.concrete_type
    assert issubclass(type_, list)
    assert len(annotation_info.arg_annotations) == 1

    arg = annotation_info.arg_annotations[0]
    validated_objs = [context.validate_obj(o, arg) for o in obj]

    if isinstance(obj, type_) and all(o is n for o, n in zip(obj, validated_objs)):
        return obj
    elif type_ is list:
        return validated_objs
    return type_(validated_objs)


def _validate_tuple(
    obj: ValueCollectionType,
    annotation_info: Annotation,
    context: ConversionContext,
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
            context.validate_obj(o, arg)
            for o, arg in zip(sized_obj, annotation_info.arg_annotations)
        )
    else:
        # homogeneous tuple like tuple[int, ...]
        assert len(annotation_info.arg_annotations) == 2
        arg = annotation_info.arg_annotations[0]
        validated_objs = tuple(context.validate_obj(o, arg) for o in obj)

    if isinstance(obj, type_) and all(o is n for o, n in zip(obj, validated_objs)):
        return obj
    elif type_ is tuple:
        return validated_objs
    return type_(validated_objs)


def _validate_set(
    obj: ValueCollectionType,
    annotation_info: Annotation,
    context: ConversionContext,
) -> set[Any]:
    type_ = annotation_info.concrete_type
    assert issubclass(type_, set)
    assert len(annotation_info.arg_annotations) == 1

    arg = annotation_info.arg_annotations[0]
    validated_objs = {context.validate_obj(o, arg) for o in obj}

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
    context: ConversionContext,
) -> dict:
    type_ = annotation_info.concrete_type
    assert issubclass(type_, dict)
    assert len(annotation_info.arg_annotations) == 2
    key_type, value_type = annotation_info.arg_annotations

    validated_objs = {
        context.validate_obj(k, key_type): context.validate_obj(v, value_type)
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


def _convert_obj(
    obj: Any, annotation_info: Annotation, context: ConversionContext
) -> Any:
    """
    Convert object by invoking converters and built-in handling, raising `ValueError`
    if it could not be converted.
    """
    # try user-provided converters
    if converter := _find_converter(
        obj, annotation_info.concrete_type, context.converters
    ):
        return converter.convert(obj, annotation_info, context)

    # if lenient, keep trying
    if context.lenient:
        # built-in converters
        if converter := _find_converter(
            obj, annotation_info.concrete_type, BUILTIN_CONVERTERS
        ):
            return converter.convert(obj, annotation_info, context)

        # direct object construction
        return annotation_info.concrete_type(obj)

    raise ValueError(
        f"Object '{obj}' ({type(obj)}) could not be converted to {annotation_info}"
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

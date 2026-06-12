"""
Library of builtin converters.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields
from datetime import date, datetime, time
from functools import cache
from typing import Any, Protocol, TypeVar, cast, get_type_hints, runtime_checkable

from ..inspecting.annotations import Annotation
from ..types import DataclassProtocol, ValueCollectionType
from ._types import ERROR_SENTINEL, ErrorSentinel
from .converter.symmetric import BaseSymmetricTypeConverter
from .converter.type import MatchSpec
from .serializer import SerializationFrame, TypeSerializer, TypeSerializerRegistry
from .utils import convert_to_dict, convert_to_list, convert_to_set, convert_to_tuple
from .validator import TypeValidator, TypeValidatorRegistry, ValidationFrame

__all__ = [
    "DateConverter",
    "DateTimeConverter",
    "TimeConverter",
    "DataclassConverter",
    "IntConverter",
    "FloatConverter",
    "BoolConverter",
    "StrConverter",
    "ListConverter",
    "TupleConverter",
    "SetConverter",
    "FrozenSetConverter",
    "DictConverter",
    "BUILTIN_SYMMETRIC_CONVERTERS",
    "BUILTIN_SERIALIZERS",
    "get_builtin_converters",
    "get_builtin_validator_registry",
    "get_builtin_serializer_registry",
]


class DateConverter(BaseSymmetricTypeConverter[str, date]):
    """
    Converter for ISO date strings to/from python date objects.
    """

    @classmethod
    def validate(cls, obj: str, _: ValidationFrame) -> date:
        return date.fromisoformat(obj)

    @classmethod
    def serialize(cls, obj: date, _: SerializationFrame) -> str:
        return obj.isoformat()


class DateTimeConverter(BaseSymmetricTypeConverter[str, datetime]):
    """
    Converter for ISO datetime strings to/from python datetime objects.
    """

    @classmethod
    def validate(cls, obj: str, _: ValidationFrame) -> datetime:
        return datetime.fromisoformat(obj)

    @classmethod
    def serialize(cls, obj: datetime, _: SerializationFrame) -> str:
        return obj.isoformat()


class TimeConverter(BaseSymmetricTypeConverter[str, time]):
    """
    Converter for ISO time strings to/from python time objects, i.e. `HH:MM:SS` or
    `HH:MM:SS.ffffff`.
    """

    @classmethod
    def validate(cls, obj: str, _: ValidationFrame) -> time:
        return time.fromisoformat(obj)

    @classmethod
    def serialize(cls, obj: time, _: SerializationFrame) -> str:
        return obj.isoformat()


class DataclassConverter(BaseSymmetricTypeConverter[Mapping[str, Any], DataclassProtocol]):
    """
    Converter for dictionaries to/from dataclass instances.

    Recursively validates and serializes all fields based on their type annotations.
    """

    validation_match_spec = MatchSpec(narrowable_target=True)

    @classmethod
    def validate(
        cls,
        obj: Mapping[str, Any],
        frame: ValidationFrame,
        /,
    ) -> DataclassProtocol:
        """
        Recursively validate mapping to dataclass instance.
        """
        # get the target dataclass type
        dataclass_type = frame.target_annotation.concrete_type

        # get type hints for the dataclass fields
        type_hints = get_type_hints(dataclass_type)

        # get dataclass fields
        dataclass_fields = fields(dataclass_type)

        # validate each field
        validated_fields: dict[str, Any] = {}
        for field in dataclass_fields:
            field_name = field.name

            # check if field is present in input
            if field_name not in obj:
                # let TypeError be raised later upon __init__, which will aggregate
                # all missing arguments
                continue

            # get field's type annotation
            field_type = type_hints.get(field_name, Any)
            field_annotation = Annotation(field_type)

            # recurse to validate the field value
            validated_obj = frame.recurse(
                obj[field_name],
                field_name,
                target_annotation=field_annotation,
            )
            validated_fields[field_name] = validated_obj

        # construct dataclass instance (error sentinels handled downstream)
        return dataclass_type(**validated_fields)

    @classmethod
    def serialize(
        cls,
        obj: DataclassProtocol,
        frame: SerializationFrame,
        /,
    ) -> dict[str, Any]:
        """
        Recursively serialize dataclass instance to dictionary.
        """
        # get type hints for the dataclass fields
        dataclass_type = type(obj)
        type_hints = get_type_hints(dataclass_type)

        # serialize each field
        serialized_fields: dict[str, Any] = {}
        for field in fields(obj):
            field_name = field.name
            field_obj = getattr(obj, field_name)

            # get field's type annotation
            field_type = type_hints.get(field_name, Any)
            field_annotation = Annotation(field_type)

            # recurse to serialize the field value
            serialized_value = frame.recurse(
                field_obj,
                field_name,
                source_annotation=field_annotation,
            )
            serialized_fields[field_name] = serialized_value

        return serialized_fields


class IntConverter:
    """
    Converts str/bytes/bytearray to int, supporting hex (0x), octal (0o), and binary
    (0b) prefixes via base-0 inference.
    """

    @classmethod
    def _validate(cls, obj: str | bytes | bytearray) -> int:
        return int(obj, 0)

    @classmethod
    def as_validator(cls) -> TypeValidator[str | bytes | bytearray, int]:
        return TypeValidator(str | bytes | bytearray, int, func=cls._validate)


class FloatConverter:
    """
    Converts str or int to float.
    """

    @classmethod
    def as_validator(cls) -> TypeValidator[str | int, float]:
        return TypeValidator(str | int, float)


class BoolConverter:
    """
    Converts any object to bool.
    """

    @classmethod
    def as_validator(cls) -> TypeValidator[Any, bool]:
        return TypeValidator(Any, bool, match_spec=MatchSpec(widenable_target=False))


class StrConverter:
    """
    Converts any object to str.
    """

    @classmethod
    def as_validator(cls) -> TypeValidator[Any, str]:
        return TypeValidator(Any, str)


class ListConverter:
    """
    Converts collection types to list.
    """

    @classmethod
    def as_validator(cls) -> TypeValidator:
        return TypeValidator(ValueCollectionType, list, func=convert_to_list)


class TupleConverter:
    """
    Converts collection types to tuple.
    """

    @classmethod
    def as_validator(cls) -> TypeValidator:
        return TypeValidator(ValueCollectionType, tuple, func=convert_to_tuple)


class SetConverter:
    """
    Converts collection types to set.
    """

    @classmethod
    def as_validator(cls) -> TypeValidator:
        return TypeValidator(ValueCollectionType, set, func=convert_to_set)


class FrozenSetConverter:
    """
    Converts collection types to frozenset.
    """

    @classmethod
    def as_validator(cls) -> TypeValidator:
        return TypeValidator(ValueCollectionType, frozenset, func=convert_to_set)


class DictConverter:
    """
    Converts mapping types to dict.
    """

    @classmethod
    def as_validator(cls) -> TypeValidator:
        return TypeValidator(Mapping, dict, func=convert_to_dict)


_T_contra = TypeVar("_T_contra", contravariant=True)


# technically only one of __lt__/__gt__ is required
@runtime_checkable
class SupportsComparison(Protocol[_T_contra]):
    def __lt__(self, other: _T_contra, /) -> bool: ...
    def __gt__(self, other: _T_contra, /) -> bool: ...


def serialize_to_list(
    obj: ValueCollectionType, frame: SerializationFrame
) -> list | ErrorSentinel:
    """
    Serialize to list with optional sorting.
    """
    obj_list = convert_to_list(obj, frame)
    if isinstance(obj_list, ErrorSentinel):
        return ERROR_SENTINEL

    if isinstance(obj, (set, frozenset)) and frame.params.sort_sets:
        for o in obj_list:
            if not isinstance(o, SupportsComparison):
                raise ValueError(
                    f"Object '{o}' does not support comparison, so containing set cannot be converted to a sorted list"
                )
        return sorted(cast(list[SupportsComparison], obj_list))
    else:
        return obj_list


BUILTIN_SYMMETRIC_CONVERTERS: tuple[type[BaseSymmetricTypeConverter], ...] = (
    TimeConverter,
    DateTimeConverter,
    DateConverter,
    DataclassConverter,
)

BUILTIN_SERIALIZERS = (
    TypeSerializer(set | frozenset | tuple, list, func=serialize_to_list),
)
"""
Extra serializers to use for json serialization.
"""


def get_model_converter() -> type[BaseSymmetricTypeConverter]:
    """
    Get converter for `BaseModel`; must be lazy-loaded to avoid circular dependency.
    """
    from ..model.base import ModelConverter

    return ModelConverter


def get_builtin_converters() -> tuple[type[BaseSymmetricTypeConverter], ...]:
    return (*BUILTIN_SYMMETRIC_CONVERTERS, get_model_converter())


@cache
def get_builtin_validator_registry() -> TypeValidatorRegistry:
    return TypeValidatorRegistry(*(c.as_validator() for c in get_builtin_converters()))


@cache
def get_builtin_serializer_registry() -> TypeSerializerRegistry:
    return TypeSerializerRegistry(
        *(c.as_serializer() for c in get_builtin_converters()), *BUILTIN_SERIALIZERS
    )

"""
Library of builtin converters.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields
from datetime import date, datetime, time
from functools import cache
from typing import (
    Any,
    Iterable,
    Protocol,
    TypeVar,
    cast,
    get_type_hints,
    runtime_checkable,
)

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
    "DATACLASS_VALIDATOR",
    "DATACLASS_SERIALIZER",
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


def _validate_dataclass(
    obj: Mapping[str, Any], frame: ValidationFrame
) -> DataclassProtocol:
    dataclass_type = frame.target_annotation.concrete_type
    type_hints = get_type_hints(dataclass_type)
    dataclass_fields = fields(dataclass_type)

    validated_fields: dict[str, Any] = {}
    for field in dataclass_fields:
        field_name = field.name
        if field_name not in obj:
            # let TypeError be raised later upon __init__, which will aggregate
            # all missing arguments
            continue
        field_annotation = Annotation(type_hints.get(field_name, Any))
        validated_obj = frame.recurse(
            obj[field_name],
            field_name,
            target_annotation=field_annotation,
        )
        validated_fields[field_name] = validated_obj

    return dataclass_type(**validated_fields)


def _serialize_dataclass(
    obj: DataclassProtocol, frame: SerializationFrame
) -> dict[str, Any]:
    dataclass_type = type(obj)
    type_hints = get_type_hints(dataclass_type)

    serialized_fields: dict[str, Any] = {}
    for field in fields(obj):
        field_name = field.name
        field_annotation = Annotation(type_hints.get(field_name, Any))
        serialized_fields[field_name] = frame.recurse(
            getattr(obj, field_name),
            field_name,
            source_annotation=field_annotation,
        )

    return serialized_fields


DATACLASS_VALIDATOR = TypeValidator(
    Mapping[str, Any],
    DataclassProtocol,
    func=_validate_dataclass,
    match_spec=MatchSpec(narrowable_target=True),
)

DATACLASS_SERIALIZER = TypeSerializer(
    DataclassProtocol,
    dict[str, Any],
    func=_serialize_dataclass,
)


_T_contra = TypeVar("_T_contra", contravariant=True)


# technically only one of __lt__/__gt__ is required
@runtime_checkable
class SupportsComparison(Protocol[_T_contra]):
    def __lt__(self, other: _T_contra, /) -> bool: ...
    def __gt__(self, other: _T_contra, /) -> bool: ...


def _serialize_to_list(
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


# collection validators
LIST_VALIDATOR = TypeValidator(Iterable, list, func=convert_to_list)
TUPLE_VALIDATOR = TypeValidator(Iterable, tuple, func=convert_to_tuple)
SET_VALIDATOR = TypeValidator(Iterable, set, func=convert_to_set)
FROZENSET_VALIDATOR = TypeValidator(Iterable, frozenset, func=convert_to_set)
DICT_VALIDATOR = TypeValidator(Mapping, dict, func=convert_to_dict)

# collection serializers
LIST_SERIALIZER = TypeSerializer(set | frozenset | tuple, list, func=_serialize_to_list)


_BUILTIN_SYMMETRIC_CONVERTERS: tuple[type[BaseSymmetricTypeConverter], ...] = (
    TimeConverter,
    DateTimeConverter,
    DateConverter,
)
"""
Converters to use for symmetric validation/serialization.
"""

BUILTIN_SERIALIZERS = (LIST_SERIALIZER,)
"""
Extra serializers to use for json serialization.
"""


def _get_model_converter() -> type[BaseSymmetricTypeConverter]:
    """
    Get converter for `BaseModel`; must be lazy-loaded to avoid circular dependency.
    """
    from ..model.base import ModelConverter

    return ModelConverter


def _get_builtin_converters() -> tuple[type[BaseSymmetricTypeConverter], ...]:
    return (*_BUILTIN_SYMMETRIC_CONVERTERS, _get_model_converter())


@cache
def get_builtin_validator_registry() -> TypeValidatorRegistry:
    return TypeValidatorRegistry(
        DATACLASS_VALIDATOR,
        *(c.as_validator() for c in _get_builtin_converters()),
    )


@cache
def get_builtin_serializer_registry() -> TypeSerializerRegistry:
    return TypeSerializerRegistry(
        DATACLASS_SERIALIZER,
        *(c.as_serializer() for c in _get_builtin_converters()),
        *BUILTIN_SERIALIZERS,
    )

"""
Library of builtin converters.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import date, datetime, time
from typing import Any, get_type_hints

from ..inspecting.annotations import Annotation
from ..types import DataclassProtocol
from .converter import MatchSpec
from .serializer import SerializationFrame
from .symmetric_converter import BaseSymmetricConverter
from .validator import ValidationFrame


class DateConverter(BaseSymmetricConverter[str, date]):
    """
    Converter for ISO date strings to/from python date objects.
    """

    @classmethod
    def validate(cls, obj: str, _: ValidationFrame) -> date:
        return date.fromisoformat(obj)

    @classmethod
    def serialize(cls, obj: date, _: SerializationFrame) -> str:
        return obj.isoformat()


class DateTimeConverter(BaseSymmetricConverter[str, datetime]):
    """
    Converter for ISO datetime strings to/from python datetime objects.
    """

    @classmethod
    def validate(cls, obj: str, _: ValidationFrame) -> datetime:
        return datetime.fromisoformat(obj)

    @classmethod
    def serialize(cls, obj: datetime, _: SerializationFrame) -> str:
        return obj.isoformat()


class TimeConverter(BaseSymmetricConverter[str, time]):
    """
    Converter for ISO time strings to/from python time objects, i.e. `HH:MM:SS`
    or `HH:MM:SS.ffffff`.
    """

    @classmethod
    def validate(cls, obj: str, _: ValidationFrame) -> time:
        return time.fromisoformat(obj)

    @classmethod
    def serialize(cls, obj: time, _: SerializationFrame) -> str:
        return obj.isoformat()


class DataclassConverter(BaseSymmetricConverter[dict[str, Any], DataclassProtocol]):
    """
    Converter for dictionaries to/from dataclass instances.

    Recursively validates and serializes all fields based on their type annotations.
    """

    validation_match_spec = MatchSpec(match_target_subtype=True)

    @classmethod
    def validate(
        cls,
        obj: dict[str, Any],
        frame: ValidationFrame,
        /,
    ) -> DataclassProtocol:
        """
        Recursively validate dictionary to dataclass instance.
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

        # construct dataclass instance
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


BUILTIN_CONVERTERS: tuple[type[BaseSymmetricConverter], ...] = (
    DateConverter,
    DateTimeConverter,
    TimeConverter,
    DataclassConverter,
)

BUILTIN_VALIDATORS = tuple(c.as_validator() for c in BUILTIN_CONVERTERS)
BUILTIN_SERIALIZERS = tuple(c.as_serializer() for c in BUILTIN_CONVERTERS)

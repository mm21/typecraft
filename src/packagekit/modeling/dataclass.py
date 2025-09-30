from __future__ import annotations

import dataclasses
from dataclasses import Field, dataclass
from functools import cache, cached_property
from typing import (
    Any,
    Self,
    dataclass_transform,
    get_type_hints,
)

from ..typing.generics import AnnotationInfo
from .normalizing import Converter, normalize_obj

__all__ = [
    "FieldInfo",
    "BaseValidatedDataclass",
]


@dataclass(kw_only=True)
class FieldInfo:
    """
    Field info with annotations processed.
    """

    field: Field
    """
    Dataclass field.
    """

    annotation_info: AnnotationInfo
    """
    Annotation info.
    """

    @classmethod
    def from_field(
        cls, obj_cls: type[BaseValidatedDataclass], field: Field
    ) -> FieldInfo:
        """
        Get field info from field.
        """
        assert field.type, f"Field '{field.name}' does not have an annotation"
        type_hints = get_type_hints(obj_cls, include_extras=True)

        assert field.name in type_hints
        annotation = type_hints[field.name]
        annotation_info = AnnotationInfo(annotation)

        return FieldInfo(field=field, annotation_info=annotation_info)


@dataclass_transform(kw_only_default=True)
class BaseValidatedDataclass:
    """
    Base class to transform subclass to dataclass and provide field and data validation.
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls = dataclass(cls, kw_only=True)

        # validate fields
        for field in _get_fields(cls):
            if not field.type:
                raise TypeError(
                    f"Class {cls}: Field '{field.name}': No type annotation"
                )

    def __new__(cls, *args, **kwargs) -> Self:
        _, _ = (args, kwargs)
        # validate fields before proceeding with object creation
        if valid_types := cls.dataclass_get_valid_types():
            for name, field_info in cls.dataclass_get_fields().items():
                for field_type in field_info.annotation_info.types:
                    if not issubclass(field_type, valid_types):
                        raise TypeError(
                            f"Class {cls}: Field '{name}': Type ({field_type}) not one of {valid_types}"
                        )
        return super().__new__(cls)

    def __setattr__(self, name: str, value: Any):
        field_info = self.dataclass_fields.get(name)

        # if this is a field, normalize and validate value
        if field_info:
            value_norm = self.__normalize_value(field_info, value)
            if not isinstance(value_norm, field_info.annotation_info.types):
                raise ValueError(
                    f"Field '{field_info.field.name}' of object {self}: Value '{value}' "
                    f"({type(value)}) not allowed and could not be converted, expected "
                    f"one of {field_info.annotation_info.types}"
                )
        else:
            value_norm = value

        super().__setattr__(name, value_norm)

    @cached_property
    def dataclass_fields(self) -> dict[str, FieldInfo]:
        """
        Dataclass fields with annotations resolved and processed.
        """
        return type(self).dataclass_get_fields()

    @classmethod
    def dataclass_get_fields(cls) -> dict[str, FieldInfo]:
        """
        Get dataclass fields from class.
        """
        return cls.__dataclass_fields()

    @classmethod
    def dataclass_get_valid_types(cls) -> tuple[Any, ...]:
        """
        Override to restrict allowed field types; allow any types if empty.
        """
        return tuple()

    def dataclass_get_converters(self) -> tuple[Converter[Any], ...]:
        """
        Override to provide converters for values.
        """
        return tuple()

    def dataclass_normalize(self, field_info: FieldInfo, value: Any) -> Any:
        """
        Override to handle custom field normalization.
        """
        _ = field_info
        return value

    @cached_property
    def _converters(self) -> tuple[Converter[Any], ...]:
        return self.dataclass_get_converters()

    @classmethod
    @cache
    def __dataclass_fields(cls) -> dict[str, FieldInfo]:
        """
        Implementation of API to keep the `dataclass_fields` signature intact,
        overridden by `@cache`.
        """
        return {f.name: FieldInfo.from_field(cls, f) for f in _get_fields(cls)}

    def __normalize_value(self, field_info: FieldInfo, value: Any) -> Any:
        """
        Normalize value to the type expected by this field.
        """
        # invoke custom normalizer
        value_ = self.dataclass_normalize(field_info, value)

        # if not an expected type, attempt to convert
        if not isinstance(value_, field_info.annotation_info.types):
            for type_ in field_info.annotation_info.types:
                for converter in self._converters:
                    if converter.can_convert(value_, type_):
                        return normalize_obj(value_, type_, converter)

        return value_


def _get_fields(class_or_instance: Any) -> tuple[Field, ...]:
    """
    Wrapper for `dataclasses.fields()` to enable type checking in case type checkers
    aren't aware `class_or_instance` is actually a dataclass.
    """
    return dataclasses.fields(class_or_instance)

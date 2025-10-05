from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import Field, dataclass
from functools import cache, cached_property
from typing import (
    Any,
    dataclass_transform,
    get_type_hints,
)

from .typing_utils import AnnotationInfo
from .validating import Converter, ValidationContext, validate_obj

__all__ = [
    "FieldInfo",
    "DataclassConfig",
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


@dataclass(kw_only=True)
class DataclassConfig:
    """
    Configures dataclass.
    """

    lenient: bool = False
    """
    Coerce values to expected type if possible.
    """

    validate_on_assignment: bool = False
    """
    Validate when attributes are set, not just when the class is created.
    """


@dataclass_transform(kw_only_default=True)
class BaseValidatedDataclass:
    """
    Base class to transform subclass to dataclass and provide recursive field
    validation.
    """

    dataclass_config: DataclassConfig = DataclassConfig()
    """
    Set on subclass to configure this dataclass.
    """

    __init_done: bool = False
    """
    Whether initialization has completed.
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

    def __post_init__(self):
        self.__init_done = True

    def __setattr__(self, name: str, value: Any):
        field_info = self.dataclass_fields.get(name)

        # validate value if applicable
        if field_info and (
            not self.__init_done or self.dataclass_config.validate_on_assignment
        ):
            value_ = validate_obj(
                value,
                field_info.annotation_info.annotation,
                *self.__converters,
                lenient=self.dataclass_config.lenient,
            )
        else:
            value_ = value

        super().__setattr__(name, value_)

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

    def dataclass_get_converters(self) -> tuple[Converter[Any], ...]:
        """
        Override to provide converters for values.
        """
        return tuple()

    @cached_property
    def __converters(self) -> tuple[Converter[Any], ...]:
        # add converter for nested dataclasses at end in case user passes a
        # converter for a subclass
        return (*self.dataclass_get_converters(), NESTED_DATACLASS_CONVERTER)

    @classmethod
    @cache
    def __dataclass_fields(cls) -> dict[str, FieldInfo]:
        """
        Implementation of API to keep the `dataclass_fields` signature intact,
        overridden by `@cache`.
        """
        return {f.name: FieldInfo.from_field(cls, f) for f in _get_fields(cls)}


def convert_dataclass(
    obj: Any, annotation_info: AnnotationInfo, _: ValidationContext
) -> BaseValidatedDataclass:
    type_ = annotation_info.concrete_type
    assert issubclass(type_, BaseValidatedDataclass)
    assert isinstance(obj, Mapping)
    return type_(**obj)


NESTED_DATACLASS_CONVERTER = Converter(
    BaseValidatedDataclass, (Mapping,), func=convert_dataclass
)
"""
Converts a mapping (e.g. dict) to a validated dataclass.
"""


def _get_fields(class_or_instance: Any) -> tuple[Field, ...]:
    """
    Wrapper for `dataclasses.fields()` to enable type checking in case type checkers
    aren't aware `class_or_instance` is actually a dataclass.
    """
    return dataclasses.fields(class_or_instance)

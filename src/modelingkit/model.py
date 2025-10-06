from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import Field, dataclass
from functools import cache, cached_property
from typing import (
    Any,
    Self,
    TypedDict,
    dataclass_transform,
    get_type_hints,
)

from .typing_utils import AnnotationInfo
from .validating import Converter, ValidationContext, validate_obj

__all__ = [
    "FieldInfo",
    "ModelConfig",
    "BaseModel",
]


class FieldMetadata(TypedDict):
    """
    Encapsulates metadata for a field definition. Pass into dataclass's `field` via
    `metadata` argument.
    """

    alias: str
    """
    Field name to use when loading a dumping from/to dict.
    """


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

    def get_name(self, *, by_alias: bool = False) -> str:
        """
        Get this field's name, optionally using its alias.
        """
        return (
            self.field.metadata.get("alias", self.field.name)
            if by_alias
            else self.field.name
        )

    @classmethod
    def _from_field(cls, obj_cls: type[BaseModel], field: Field) -> FieldInfo:
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
class ModelConfig:
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
class BaseModel:
    """
    Base class to transform subclass to dataclass and provide recursive field
    validation.
    """

    dataclass_config: ModelConfig = ModelConfig()
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
            value_ = self.dataclass_pre_validate(field_info, value)
            value_ = validate_obj(
                value_,
                field_info.annotation_info.annotation,
                *self.__converters,
                lenient=self.dataclass_config.lenient,
            )
            value_ = self.dataclass_post_validate(field_info, value_)
        else:
            value_ = value

        super().__setattr__(name, value_)

    @classmethod
    def dataclass_load(cls, obj: Mapping, /, *, by_alias: bool = False) -> Self:
        """
        Create instance of dataclass from mapping, substituting aliases if
        `by_alias` is `True`.
        """
        values: dict[str, Any] = {}

        for name, field_info in cls.dataclass_get_fields().items():
            mapping_name = field_info.get_name(by_alias=by_alias)
            if mapping_name in obj:
                values[name] = obj[mapping_name]

        return cls(**values)

    @classmethod
    def dataclass_get_fields(cls) -> dict[str, FieldInfo]:
        """
        Get dataclass fields from class.
        """
        return cls.__dataclass_fields()

    @cached_property
    def dataclass_fields(self) -> dict[str, FieldInfo]:
        """
        Get dataclass fields from instance.
        """
        return type(self).dataclass_get_fields()

    def dataclass_dump(self, *, by_alias: bool = False) -> dict[str, Any]:
        """
        Dump dataclass to dictionary, substituting aliases if `by_alias` is `True`.
        """
        values: dict[str, Any] = {}

        for name, field_info in self.dataclass_fields.items():
            mapping_name = field_info.get_name(by_alias=by_alias)
            values[mapping_name] = getattr(self, name)

        return values

    def dataclass_get_converters(self) -> tuple[Converter[Any], ...]:
        """
        Override to provide converters for values by type, including inner values like
        elements of lists.
        """
        return tuple()

    def dataclass_pre_validate(self, field_info: FieldInfo, value: Any) -> Any:
        """
        Override to perform validation on value before built-in validation.
        """
        _ = field_info
        return value

    def dataclass_post_validate(self, field_info: FieldInfo, value: Any) -> Any:
        """
        Override to perform validation on value after built-in validation.
        """
        _ = field_info
        return value

    @classmethod
    @cache
    def __dataclass_fields(cls) -> dict[str, FieldInfo]:
        """
        Implementation of API to keep the `dataclass_fields` signature intact,
        overridden by `@cache`.
        """
        return {f.name: FieldInfo._from_field(cls, f) for f in _get_fields(cls)}

    @cached_property
    def __converters(self) -> tuple[Converter[Any], ...]:
        """
        Converters to use for validation.
        """
        # add converter for nested dataclasses at end in case user passes a
        # converter for a subclass
        return (*self.dataclass_get_converters(), NESTED_DATACLASS_CONVERTER)


def convert_dataclass(
    obj: Any, annotation_info: AnnotationInfo, _: ValidationContext
) -> BaseModel:
    type_ = annotation_info.concrete_type
    assert issubclass(type_, BaseModel)
    assert isinstance(obj, Mapping)
    return type_(**obj)


NESTED_DATACLASS_CONVERTER = Converter(BaseModel, (Mapping,), func=convert_dataclass)
"""
Converts a mapping (e.g. dict) to a validated dataclass.
"""


def _get_fields(class_or_instance: Any) -> tuple[Field, ...]:
    """
    Wrapper for `dataclasses.fields()` to enable type checking in case type checkers
    aren't aware `class_or_instance` is actually a dataclass.
    """
    return dataclasses.fields(class_or_instance)

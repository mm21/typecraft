from __future__ import annotations

import dataclasses
from dataclasses import Field, dataclass
from functools import cache
from types import UnionType
from typing import (
    Annotated,
    Any,
    Self,
    dataclass_transform,
    get_args,
    get_origin,
    get_type_hints,
)

from ..data.normalizing import Converter, normalize_obj

__all__ = [
    "FieldInfo",
    "BaseValidatedDataclass",
    "get_fields",
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

    annotation: Any
    """
    Original annotation after stripping `Annotated[]` if applicable.
    """

    extras: tuple[Any, ...]
    """
    Extra annotations, if `Annotated[]` was used.
    """

    annotations: tuple[Any, ...]
    """
    Annotation(s) with unions flattened if applicable.
    """

    concrete_annotations: tuple[type[Any], ...]
    """
    Concrete (non-generic) annotation(s) with unions flattened if applicable.
    """

    @classmethod
    def _from_field(
        cls, obj_cls: type[BaseValidatedDataclass], field: Field
    ) -> FieldInfo:
        """
        Get field info from field.
        """
        assert field.type, f"Field '{field.name}' does not have an annotation"
        type_hints = get_type_hints(obj_cls, include_extras=True)

        assert field.name in type_hints
        annotation = type_hints[field.name]

        # get extras if applicable
        if get_origin(annotation) is Annotated:
            args = get_args(annotation)
            assert len(args)

            annotation = args[0]
            extras = tuple(args[1:])
        else:
            extras = ()

        if type(annotation) is UnionType:
            annotations = get_args(annotation)
        else:
            annotations = (annotation,)

        concrete_annotations = tuple(get_origin(a) or a for a in annotations)

        return FieldInfo(
            field=field,
            annotation=annotation,
            extras=extras,
            annotations=annotations,
            concrete_annotations=concrete_annotations,
        )


@dataclass_transform(kw_only_default=True)
class BaseValidatedDataclass:
    """
    Base class to transform subclass to dataclass and provide field and data validation.
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls = dataclass(cls, kw_only=True)

        # validate fields
        for field in get_fields(cls):
            if not field.type:
                raise TypeError(
                    f"Class {cls}: Field '{field.name}': No type annotation"
                )

    def __new__(cls, *args, **kwargs) -> Self:
        _, _ = (args, kwargs)
        # validate fields before proceeding with object creation
        if valid_types := cls.dataclass_valid_types():
            for name, field_info in cls.dataclass_fields().items():
                for field_type in field_info.concrete_annotations:
                    if not issubclass(field_type, valid_types):
                        raise TypeError(
                            f"Class {cls}: Field '{name}': Type ({field_type}) not one of {valid_types}"
                        )
        return super().__new__(cls)

    def __setattr__(self, name: str, value: Any):
        field_info = type(self).dataclass_fields().get(name)

        # if this is a field, normalize and validate value
        if field_info:
            value_norm = self.__normalize_value(field_info, value)
            if not isinstance(value_norm, field_info.concrete_annotations):
                raise ValueError(
                    f"Field '{field_info.field.name}' of object {self}: Value '{value_norm}' "
                    f"({type(value_norm)}) not allowed, expected one of "
                    f"{field_info.concrete_annotations}"
                )
        else:
            value_norm = value

        super().__setattr__(name, value_norm)

    @classmethod
    def dataclass_fields(cls) -> dict[str, FieldInfo]:
        """
        Fields of dataclass with annotations resolved and processed.
        """
        return cls.__dataclass_fields()

    @classmethod
    def dataclass_valid_types(cls) -> tuple[Any, ...]:
        """
        Override to restrict allowed field types; allow any types if empty.
        """
        return tuple()

    def dataclass_converters(self) -> tuple[Converter[Any], ...]:
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

    @classmethod
    @cache
    def __dataclass_fields(cls) -> dict[str, FieldInfo]:
        """
        Implementation of API to keep the `dataclass_fields` signature intact,
        overridden by `@cache`.
        """
        return {f.name: FieldInfo._from_field(cls, f) for f in get_fields(cls)}

    def __normalize_value(self, field_info: FieldInfo, value: Any) -> Any:
        """
        Normalize value to the type expected by this field.
        """
        # invoke custom normalizer
        value_ = self.dataclass_normalize(field_info, value)

        # if not a valid type, attempt to convert
        if not isinstance(value_, field_info.concrete_annotations) and (
            converters := self.dataclass_converters()
        ):
            for annotation in field_info.concrete_annotations:
                if any(isinstance(value_, c.from_types) for c in converters):
                    return normalize_obj(value_, annotation, *converters)

        return value_


def get_fields(class_or_instance: Any) -> tuple[Field, ...]:
    """
    Wrapper for `dataclasses.fields()` to enable type checking in case type checkers
    aren't aware `class_or_instance` is actually a dataclass.
    """
    return dataclasses.fields(class_or_instance)

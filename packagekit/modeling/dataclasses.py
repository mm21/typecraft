from __future__ import annotations

import dataclasses
from dataclasses import Field, dataclass
from functools import cached_property
from types import UnionType
from typing import Annotated, Any, get_args, get_origin, get_type_hints

from ..data.normalizer import Converter, normalize_obj


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
    def _from_field(cls, obj: BaseValidatedDataclass, field: Field) -> FieldInfo:
        """
        Get field info from field.
        """
        assert field.type, f"Field '{field.name}' does not have an annotation"
        type_hints = get_type_hints(obj, include_extras=True)

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


class BaseValidatedDataclass:
    """
    Base class to provide field and data validation.
    """

    def __setattr__(self, name: str, value: Any):
        field_info = self.dataclass_fields.get(name)

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

    @cached_property
    def dataclass_fields(self) -> dict[str, FieldInfo]:
        """
        Fields of dataclass with annotations resolved and processed.
        """
        return {f.name: FieldInfo._from_field(self, f) for f in _get_fields(self)}

    @classmethod
    def dataclass_valid_types(cls) -> tuple[Any] | None:
        """
        Override to restrict allowed field types; allow any types if `None`.
        """
        return None

    def dataclass_converters(self) -> tuple[Converter[Any]]:
        """
        Override to provide converters for values.
        """
        return tuple()

    def __normalize_value(self, field_info: FieldInfo, value: Any) -> Any:
        """
        Normalize value to the type expected by this field, raising `ValueError` if
        unexpected type and it cannot be converted.
        """
        # if not a valid type, attempt to convert
        if not isinstance(value, field_info.concrete_annotations) and (
            converters := self.dataclass_converters()
        ):
            for annotation in field_info.concrete_annotations:
                if any(isinstance(value, c.from_types) for c in converters):
                    return normalize_obj(value, annotation, *converters)
        return value


def _get_fields(class_or_instance: Any) -> tuple[Field[Any], ...]:
    """
    Wrapper since base classes are not themselves dataclasses.
    """
    if not hasattr(class_or_instance, "__dataclass_fields__"):
        raise TypeError(f"Not a dataclass: {class_or_instance}")
    return dataclasses.fields(class_or_instance)

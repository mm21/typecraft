"""
Dataclass-based data models with validation.

TODO:
- Decorators to register validators/serializers (model and field level)
    - Remove model_[pre/post]_validate()
- Type-based serialization mechanism
- Built-in validation helpers (comparison, range, ...)
- Lambda-based validation (return True if valid)
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import MISSING, dataclass
from functools import cache, cached_property
from typing import (
    Any,
    Callable,
    Self,
    dataclass_transform,
    get_type_hints,
    overload,
)

from .inspecting.annotations import Annotation
from .validating import TypedValidator, ValidationContext, validate

__all__ = [
    "Field",
    "FieldInfo",
    "FieldMetadata",
    "ModelConfig",
    "BaseModel",
]


@overload
def Field[T](
    *,
    default: T,
    alias: str | None = None,
    user_metadata: Any | None = None,
    init: bool = True,
    repr: bool = True,
    hash: bool | None = None,
    compare: bool = True,
) -> T: ...


@overload
def Field[T](
    *,
    default_factory: Callable[[], T],
    alias: str | None = None,
    user_metadata: Any | None = None,
    init: bool = True,
    repr: bool = True,
    hash: bool | None = None,
    compare: bool = True,
) -> T: ...


@overload
def Field(
    *,
    alias: str | None = None,
    user_metadata: Any | None = None,
    init: bool = True,
    repr: bool = True,
    hash: bool | None = None,
    compare: bool = True,
) -> Any: ...


def Field(
    *,
    default: Any = MISSING,
    default_factory: Any = MISSING,
    alias: str | None = None,
    user_metadata: Any | None = None,
    init: bool = True,
    repr: bool = True,
    hash: bool | None = None,
    compare: bool = True,
) -> Any:
    """
    Create a new field. Wraps a dataclass field along with metadata.
    """
    metadata = FieldMetadata(alias=alias, user_metadata=user_metadata)
    return dataclasses.field(
        default=default,
        default_factory=default_factory,
        init=init,
        repr=repr,
        hash=hash,
        compare=compare,
        metadata={"metadata": metadata},
    )


@dataclass(kw_only=True)
class FieldInfo:
    """
    Field info with annotations processed.
    """

    field: dataclasses.Field
    """
    Dataclass field.
    """

    annotation_info: Annotation
    """
    Annotation info.
    """

    metadata: FieldMetadata
    """
    Metadata passed to field definition.
    """

    @property
    def name(self) -> str:
        """
        Accessor for field name.
        """
        return self.field.name

    def get_name(self, *, by_alias: bool = False) -> str:
        """
        Get this field's name, optionally using its alias.
        """
        return self.metadata.alias or self.name if by_alias else self.name

    @classmethod
    def _from_field(
        cls, obj_cls: type[BaseModel], field: dataclasses.Field
    ) -> FieldInfo:
        """
        Get field info from field.
        """
        assert field.type, f"Field '{field.name}' does not have an annotation"
        type_hints = get_type_hints(obj_cls, include_extras=True)

        assert field.name in type_hints
        annotation = type_hints[field.name]
        annotation_info = Annotation(annotation)

        metadata = field.metadata.get("metadata") or FieldMetadata()
        assert isinstance(metadata, FieldMetadata)

        return FieldInfo(
            field=field, annotation_info=annotation_info, metadata=metadata
        )


@dataclass(kw_only=True)
class FieldMetadata:
    """
    Encapsulates metadata for a field definition.
    """

    alias: str | None = None
    """
    Field name to use when loading a dumping from/to dict.
    """

    user_metadata: Any | None = None
    """
    User-provided metadata.
    """


@dataclass(kw_only=True)
class ModelConfig:
    """
    Configures model.
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
    Base class to transform subclass to model and provide recursive field
    validation.
    """

    model_config: ModelConfig = ModelConfig()
    """
    Set on subclass to configure this model.
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
        field_info = self.model_fields.get(name)

        # validate value if applicable
        if field_info and (
            not self.__init_done or self.model_config.validate_on_assignment
        ):
            value_ = self.model_pre_validate(field_info, value)
            value_ = validate(
                value_,
                field_info.annotation_info.raw,
                *self.__converters,
                lenient=self.model_config.lenient,
            )
            value_ = self.model_post_validate(field_info, value_)
        else:
            value_ = value

        super().__setattr__(name, value_)

    @classmethod
    def model_load(cls, obj: Mapping, /, *, by_alias: bool = False) -> Self:
        """
        Create instance of model from mapping, substituting aliases if
        `by_alias` is `True`.
        """
        values: dict[str, Any] = {}

        for name, field_info in cls.model_get_fields().items():
            mapping_name = field_info.get_name(by_alias=by_alias)
            if mapping_name in obj:
                values[name] = obj[mapping_name]

        return cls(**values)

    @classmethod
    def model_get_fields(cls) -> dict[str, FieldInfo]:
        """
        Get model fields from class.
        """
        return cls.__model_fields()

    @cached_property
    def model_fields(self) -> dict[str, FieldInfo]:
        """
        Get model fields from instance.
        """
        return type(self).model_get_fields()

    def model_dump(self, *, by_alias: bool = False) -> dict[str, Any]:
        """
        Dump model to dictionary, substituting aliases if `by_alias` is `True`.
        """
        values: dict[str, Any] = {}

        for name, field_info in self.model_fields.items():
            value = getattr(self, name)

            # recurse if this is a nested model
            if issubclass(field_info.annotation_info.concrete_type, BaseModel):
                assert isinstance(value, BaseModel)
                value = value.model_dump()

            mapping_name = field_info.get_name(by_alias=by_alias)
            values[mapping_name] = value

        return values

    def model_get_converters(self) -> tuple[TypedValidator[Any], ...]:
        """
        Override to provide converters for values by type, including inner values like
        elements of lists.
        """
        return tuple()

    def model_pre_validate(self, field_info: FieldInfo, value: Any) -> Any:
        """
        Override to perform validation on value before built-in validation.
        """
        _ = field_info
        return value

    def model_post_validate(self, field_info: FieldInfo, value: Any) -> Any:
        """
        Override to perform validation on value after built-in validation.
        """
        _ = field_info
        return value

    @classmethod
    @cache
    def __model_fields(cls) -> dict[str, FieldInfo]:
        """
        Implementation of API to keep the `dataclass_fields` signature intact,
        overridden by `@cache`.
        """
        return {f.name: FieldInfo._from_field(cls, f) for f in _get_fields(cls)}

    @cached_property
    def __converters(self) -> tuple[TypedValidator[Any], ...]:
        """
        Converters to use for validation.
        """
        # add converter for nested dataclasses at end in case user passes a
        # converter for a subclass
        return (*self.model_get_converters(), MODEL_CONVERTER)


def convert_model(
    obj: Any, annotation_info: Annotation, _: ValidationContext
) -> BaseModel:
    type_ = annotation_info.concrete_type
    assert issubclass(type_, BaseModel)
    assert isinstance(obj, Mapping)
    return type_(**obj)


MODEL_CONVERTER = TypedValidator(Mapping, BaseModel, func=convert_model)
"""
Converts a mapping (e.g. dict) to a model.
"""


def _get_fields(class_or_instance: Any) -> tuple[dataclasses.Field, ...]:
    """
    Wrapper for `dataclasses.fields()` to enable type checking in case type checkers
    aren't aware `class_or_instance` is actually a dataclass.
    """
    return dataclasses.fields(class_or_instance)

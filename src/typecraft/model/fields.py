from __future__ import annotations

import dataclasses
from dataclasses import MISSING, dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Literal,
    cast,
    get_type_hints,
    overload,
)

from ..adapter import Adapter
from ..converting.serializer import (
    BaseSerializer,
    SerializerRegistry,
)
from ..converting.validator import BaseValidator, ValidatorRegistry
from ..inspecting.annotations import Annotation

if TYPE_CHECKING:
    from .base import BaseModel

__all__ = [
    "ValidatorModeType",
    "Field",
    "FieldMetadata",
    "FieldInfo",
    "typed_validators",
    "typed_serializers",
    "field_validator",
    "field_serializer",
]


type ValidatorModeType = Literal["before", "after"]


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
    Create a new field.

    Wraps a dataclass field along with metadata.
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


class FieldInfo:
    """
    Field info with annotations processed.
    """

    field: dataclasses.Field
    """
    Dataclass field.
    """

    annotation: Annotation
    """
    Annotation info.
    """

    metadata: FieldMetadata
    """
    Metadata passed to field definition.
    """

    _adapter: Adapter
    """
    Adapter object to wrap validation/serialization.
    """

    _field_validators: tuple[FieldValidatorInfo, ...]
    """
    Field-level validators registered via decorator.
    """

    _field_serializers: tuple[FieldSerializerInfo, ...]
    """
    Field-level serializers registered via decorator.
    """

    def __init__(
        self,
        field: dataclasses.Field,
        model_cls: type[BaseModel],
        *,
        validator_registry: ValidatorRegistry,
        serializer_registry: SerializerRegistry,
        field_validators: tuple[FieldValidatorInfo, ...],
        field_serializers: tuple[FieldSerializerInfo, ...],
    ):
        if not field.type:
            raise TypeError(f"Field '{field.name}' does not have an annotation")

        type_hints = get_type_hints(model_cls, include_extras=True)
        assert field.name in type_hints

        raw_annotation = type_hints[field.name]
        annotation = Annotation(raw_annotation)

        metadata = field.metadata.get("metadata") or FieldMetadata()
        assert isinstance(metadata, FieldMetadata)

        self.field = field
        self.annotation = annotation
        self.metadata = metadata
        self._field_validators = field_validators
        self._field_serializers = field_serializers
        self._adapter = Adapter(
            annotation,
            validation_params=model_cls.model_config.validation_params,
            serialization_params=model_cls.model_config.serialization_params,
            validator_registry=validator_registry,
            serializer_registry=serializer_registry,
        )

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

    def _get_validators(
        self, *, mode: Literal["before", "after"]
    ) -> tuple[FieldValidatorInfo, ...]:
        """
        Get field validators filtered by mode.
        """
        return tuple(v for v in self._field_validators if v.mode == mode)


@dataclass(kw_only=True)
class TypedValidatorsInfo:
    """
    Stores info about a method decorated with `@typed_validators`.
    """

    func: Callable[..., tuple[BaseValidator, ...]]
    """
    The method that returns validators.
    """


@dataclass(kw_only=True)
class TypedSerializersInfo:
    """
    Stores info about a method decorated with `@typed_serializers`.
    """

    func: Callable[..., tuple[BaseSerializer, ...]]
    """
    The method that returns serializers.
    """


# TODO: inspect func and store SignatureInfo, use when invoking
@dataclass(kw_only=True)
class FieldValidatorInfo:
    """
    Stores info about a method decorated with `@field_validator`.
    """

    func: Callable[..., Any]
    """
    The validator function.
    """

    field_names: tuple[str, ...] | None
    """
    Field names this validator applies to, or `None` to apply to all fields.
    """

    mode: ValidatorModeType
    """
    Validator mode.
    """


@dataclass(kw_only=True)
class FieldSerializerInfo:
    """
    Stores info about a method decorated with `@field_serializer`.
    """

    func: Callable[..., Any]
    """
    The serializer function.
    """

    field_names: tuple[str, ...] | None
    """
    Field names this serializer applies to, or `None` to apply to all fields.
    """


# marker attribute names for storing decorator info on class
TYPED_VALIDATORS_ATTR = "__typecraft_typed_validators__"
TYPED_SERIALIZERS_ATTR = "__typecraft_typed_serializers__"
FIELD_VALIDATOR_ATTR = "__typecraft_field_validator__"
FIELD_SERIALIZER_ATTR = "__typecraft_field_serializer__"


def typed_validators[T: Callable[..., tuple[BaseValidator, ...]]](func: T) -> T:
    """
    Decorator to register a classmethod that returns type-based validators.
    """
    func_ = func.__func__ if isinstance(func, classmethod) else func
    setattr(func_, TYPED_VALIDATORS_ATTR, TypedValidatorsInfo(func=func_))
    return cast(T, func)


def typed_serializers[T: Callable[..., tuple[BaseSerializer, ...]]](func: T) -> T:
    """
    Decorator to register a classmethod that returns type-based serializers.
    """
    func_ = func.__func__ if isinstance(func, classmethod) else func
    setattr(func_, TYPED_SERIALIZERS_ATTR, TypedSerializersInfo(func=func_))
    return cast(T, func)


# TODO: accommodate field info as optional 2nd arg of registered func
@overload
def field_validator(
    *field_names: str,
    mode: Literal["before", "after"] = "before",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...


@overload
def field_validator(
    func: Callable[..., Any],
    /,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...


def field_validator(
    func_or_name: Callable[..., Any] | str | None = None,
    *names: str,
    mode: ValidatorModeType = "before",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator to register a field-level validator.

    If field names are omitted, the validator applies to all fields.
    """

    def register(
        func: Callable[..., Any], field_names: tuple[str, ...] | None
    ) -> Callable[..., Any]:
        func_ = func.__func__ if isinstance(func, classmethod) else func
        info = FieldValidatorInfo(func=func_, field_names=field_names, mode=mode)
        setattr(func, FIELD_VALIDATOR_ATTR, info)
        return cast(Callable[..., Any], func)

    if callable(func_or_name):
        # called without parentheses: @field_validator
        assert len(names) == 0
        return register(func_or_name, None)

    # called with parentheses: @field_validator() or @field_validator("name", ...)
    all_names = (func_or_name, *names) if isinstance(func_or_name, str) else names
    assert all(isinstance(n, str) for n in all_names)

    return lambda func: register(func, all_names or None)


@overload
def field_serializer(
    *field_names: str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...


@overload
def field_serializer(
    func: Callable[..., Any],
    /,
) -> Callable[..., Any]: ...


def field_serializer(
    func_or_name: Callable[..., Any] | str | None = None,
    *names: str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]] | Callable[..., Any]:
    """
    Decorator to register a field-level serializer.

    If field names are omitted, the serializer applies to all fields.
    """

    def register(
        func: Callable[..., Any], field_names: tuple[str, ...] | None
    ) -> Callable[..., Any]:
        func_ = func.__func__ if isinstance(func, classmethod) else func
        info = FieldSerializerInfo(func=func_, field_names=field_names)
        setattr(func, FIELD_SERIALIZER_ATTR, info)
        return cast(Callable[..., Any], func)

    if callable(func_or_name):
        # called without parentheses: @field_serializer
        assert len(names) == 0
        return register(func_or_name, None)

    # called with parentheses: @field_serializer() or @field_serializer("name", ...)
    all_names = (func_or_name, *names) if isinstance(func_or_name, str) else names
    assert all(isinstance(n, str) for n in all_names)

    return lambda func: register(func, all_names or None)

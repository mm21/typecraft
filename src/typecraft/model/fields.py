from __future__ import annotations

import dataclasses
from dataclasses import MISSING, dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Literal,
    get_type_hints,
    overload,
)

from ..converting.serializer import TypeSerializerRegistry
from ..converting.validator import TypeValidatorRegistry
from ..inspecting.annotations import Annotation
from ..serializing import SerializationEngine
from ..validating import ValidationEngine
from .methods import (
    FieldSerializerInfo,
    FieldValidatorInfo,
    TypeSerializersInfo,
    TypeValidatorsInfo,
)

if TYPE_CHECKING:
    from .base import BaseModel

__all__ = [
    "Field",
    "FieldMetadata",
    "FieldInfo",
]


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

    _validation_engine: ValidationEngine
    """
    Type-based validation engine.
    """

    _serialization_engine: SerializationEngine
    """
    Type-based serialization engine..
    """

    __field_validator_infos: tuple[FieldValidatorInfo, ...]
    """
    Field-level validators registered via decorator.
    """

    __field_serializer_infos: tuple[FieldSerializerInfo, ...]
    """
    Field-level serializers registered via decorator.
    """

    def __init__(
        self,
        field: dataclasses.Field,
        model_cls: type[BaseModel],
        *,
        type_validators_infos: tuple[TypeValidatorsInfo, ...],
        type_serializers_infos: tuple[TypeSerializersInfo, ...],
        field_validator_infos: tuple[FieldValidatorInfo, ...],
        field_serializer_infos: tuple[FieldSerializerInfo, ...],
    ):
        if not field.type:
            raise TypeError(f"Field '{field.name}' does not have an annotation")

        # get annotation
        type_hints = get_type_hints(model_cls, include_extras=True)
        assert field.name in type_hints
        raw_annotation = type_hints[field.name]
        annotation = Annotation(raw_annotation)

        # get type-based validators/serializers
        type_validators = TypeValidatorsInfo.aggregate_converters(
            model_cls, type_validators_infos
        )
        type_serializers = TypeSerializersInfo.aggregate_converters(
            model_cls, type_serializers_infos
        )

        metadata = field.metadata.get("metadata") or FieldMetadata()
        assert isinstance(metadata, FieldMetadata)

        self.field = field
        self.annotation = annotation
        self.metadata = metadata
        self._validation_engine = ValidationEngine(
            registry=TypeValidatorRegistry(*type_validators)
        )
        self._serialization_engine = SerializationEngine(
            registry=TypeSerializerRegistry(*type_serializers)
        )
        self.__field_validator_infos = field_validator_infos
        self.__field_serializer_infos = field_serializer_infos

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

    def _get_validator_infos(
        self, *, mode: Literal["before", "after"]
    ) -> tuple[FieldValidatorInfo, ...]:
        """
        Get field validators filtered by mode.
        """
        return tuple(v for v in self.__field_validator_infos if v.mode == mode)

    def _get_serializer_infos(self) -> tuple[FieldSerializerInfo, ...]:
        """
        Get field serializers.
        """
        return self.__field_serializer_infos


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

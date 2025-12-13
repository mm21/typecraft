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

from ..adapter import Adapter
from ..converting.serializer import (
    SerializerRegistry,
)
from ..converting.validator import ValidatorRegistry
from ..inspecting.annotations import Annotation
from .methods import (
    FieldSerializerInfo,
    FieldValidatorInfo,
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

from __future__ import annotations

from dataclasses import dataclass
from types import NoneType
from typing import (
    Any,
)

from ..inspecting.annotations import Annotation
from .converter import (
    BaseConversionFrame,
    BaseConversionParams,
    BaseConverter,
    BaseConverterRegistry,
    FuncConverterType,
)
from .mixins import FuncConverterMixin, GenericConverterMixin

__all__ = [
    "JsonSerializableType",
    "FuncSerializerType",
    "SerializationParams",
    "SerializationFrame",
    "BaseSerializer",
    "BaseGenericSerializer",
    "Serializer",
    "SerializerRegistry",
]

type JsonSerializableType = str | int | float | bool | NoneType | list[
    JsonSerializableType
] | dict[str | int | float | bool, JsonSerializableType]
"""
Native types which can be represented in JSON format.
"""


type FuncSerializerType[SourceT] = FuncConverterType[SourceT, Any, SerializationFrame]
"""
Function which serializes the given object from a specific source type and generally
returns an object of built-in Python type.

Can optionally take `SerializationFrame` as the second argument.
"""

JSON_SERIALIZABLE_ANNOTATION = Annotation(JsonSerializableType)
"""
Annotation singleton for JSON-serializable type.
"""


@dataclass(kw_only=True)
class SerializationParams(BaseConversionParams):
    """
    Serialization params passed by user.
    """

    use_builtin_serializers: bool = True
    """
    For non-serializable types, whether to use builtin serializers like `date` to `str`.
    """

    sort_sets: bool = True
    """
    Whether to sort sets, producing deterministic output.
    """


class SerializationFrame(BaseConversionFrame[SerializationParams]):
    """
    Internal recursion state per frame.
    """

    def recurse(
        self,
        obj: Any,
        path_segment: str | int,
        /,
        *,
        source_annotation: Annotation | None = None,
        target_annotation: Annotation | None = None,
        context: Any | None = ...,
    ) -> Any:
        return super().recurse(
            obj,
            path_segment,
            source_annotation=source_annotation,
            target_annotation=target_annotation or JSON_SERIALIZABLE_ANNOTATION,
            context=context,
        )


class BaseSerializer[SourceT, TargetT](
    BaseConverter[SourceT, TargetT, SerializationFrame]
):
    """
    Base class for type-based serializers.
    """


class BaseGenericSerializer[SourceT, TargetT](
    GenericConverterMixin[SourceT, TargetT, SerializationFrame],
    BaseSerializer[SourceT, TargetT],
):
    """
    Generic serializer: subclass with type parameters to determine source/target
    type and implement `convert()`.
    """


class Serializer[SourceT, TargetT](
    FuncConverterMixin[SourceT, TargetT, SerializationFrame],
    BaseSerializer[SourceT, TargetT],
):
    """
    Function-based serializer with optional type inference.
    """


class SerializerRegistry(BaseConverterRegistry[BaseSerializer]):
    """
    Registry for managing type-based serializers.

    Provides lookup of serializers based on source and target annotations.
    """

    def __repr__(self) -> str:
        return f"SerializerRegistry(serializers={self.serializers})"

    @property
    def serializers(self) -> tuple[BaseSerializer, ...]:
        """
        Get serializers currently registered.
        """
        return tuple(self._converters)

    def register(self, serializer: BaseSerializer, /):
        """
        Register a serializer.
        """
        self._register_converter(serializer)

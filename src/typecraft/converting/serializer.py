from __future__ import annotations

from dataclasses import dataclass
from types import NoneType
from typing import (
    TYPE_CHECKING,
    Any,
)

from ..exceptions import ConversionErrorDetail
from ..inspecting.annotations import Annotation
from .converter.base import BaseConversionFrame, BaseConversionParams, FuncConverterType
from .converter.type import (
    BaseTypeConverter,
    BaseTypeConverterRegistry,
)
from .mixins import FuncConverterMixin, GenericConverterMixin

if TYPE_CHECKING:
    from ..serializing import SerializationEngine

__all__ = [
    "JsonSerializableType",
    "FuncSerializerType",
    "SerializationParams",
    "SerializationFrame",
    "BaseTypeSerializer",
    "BaseGenericTypeSerializer",
    "TypeSerializer",
    "TypeSerializerRegistry",
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

    def __init__(
        self,
        *,
        source_annotation: Annotation,
        target_annotation: Annotation | None = None,
        params: SerializationParams | None,
        context: Any | None,
        engine: SerializationEngine,
        path: tuple[str | int, ...] | None = None,
        seen: set[int] | None = None,
        errors: list[ConversionErrorDetail] | None = None,
    ):
        super().__init__(
            source_annotation=source_annotation,
            target_annotation=target_annotation or JSON_SERIALIZABLE_ANNOTATION,
            params=params,
            context=context,
            engine=engine,
            path=path,
            seen=seen,
            errors=errors,
        )

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


class BaseTypeSerializer[SourceT, TargetT](
    BaseTypeConverter[SourceT, TargetT, SerializationFrame]
):
    """
    Base class for type-based serializers.
    """


class BaseGenericTypeSerializer[SourceT, TargetT](
    GenericConverterMixin[SourceT, TargetT, SerializationFrame],
    BaseTypeSerializer[SourceT, TargetT],
):
    """
    Generic serializer: subclass with type parameters to determine source/target
    type and implement `convert()`.
    """


class TypeSerializer[SourceT, TargetT](
    FuncConverterMixin[SourceT, TargetT, SerializationFrame],
    BaseTypeSerializer[SourceT, TargetT],
):
    """
    Function-based serializer with optional type inference.
    """


class TypeSerializerRegistry(BaseTypeConverterRegistry[BaseTypeSerializer]):
    """
    Registry for managing type-based serializers.

    Provides lookup of serializers based on source and target annotations.
    """

    def __repr__(self) -> str:
        return f"SerializerRegistry(serializers={self.serializers})"

    @property
    def serializers(self) -> tuple[BaseTypeSerializer, ...]:
        """
        Get serializers currently registered.
        """
        return tuple(self._converters)

    def register(self, serializer: BaseTypeSerializer, /):
        """
        Register a serializer.
        """
        self._register_converter(serializer)

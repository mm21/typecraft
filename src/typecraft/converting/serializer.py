from __future__ import annotations

from dataclasses import dataclass
from types import NoneType
from typing import (
    Any,
    Protocol,
    TypeVar,
    cast,
    overload,
    runtime_checkable,
)

from typecraft.types import ValueCollectionType

from ..inspecting.annotations import Annotation
from .converter import (
    BaseConversionFrame,
    BaseConverter,
    BaseConverterRegistry,
    FuncConverterType,
)
from .mixins import FuncConverterMixin, GenericConverterMixin
from .utils import convert_to_list

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
returns an object of built-in Python type. Can optionally take
`SerializationFrame` as the second argument.
"""

JSON_SERIALIZABLE_ANNOTATION = Annotation(JsonSerializableType)
"""
Annotation singleton for JSON-serializable type.
"""

_T_contra = TypeVar("_T_contra", contravariant=True)


# technically only one of __lt__/__gt__ is required
@runtime_checkable
class SupportsComparison(Protocol[_T_contra]):
    def __lt__(self, other: _T_contra, /) -> bool: ...
    def __gt__(self, other: _T_contra, /) -> bool: ...


@dataclass(kw_only=True)
class SerializationParams:
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
    Registry for managing type serializers.

    Provides efficient lookup of serializers based on source object type
    and source annotation.
    """

    def __repr__(self) -> str:
        return f"SerializerRegistry(serializers={self._converters})"

    @property
    def serializers(self) -> list[BaseSerializer]:
        """
        Get serializers currently registered.
        """
        return self._converters

    @overload
    def register(self, serializer: BaseSerializer, /): ...

    @overload
    def register(
        self,
        func: FuncSerializerType,
        /,
        *,
        match_source_subtype: bool = True,
        match_target_subtype: bool = False,
    ): ...

    def register(
        self,
        serializer_or_func: BaseSerializer | FuncSerializerType,
        /,
        *,
        match_source_subtype: bool = True,
        match_target_subtype: bool = False,
    ):
        """
        Register a serializer.
        """
        serializer = (
            serializer_or_func
            if isinstance(serializer_or_func, BaseSerializer)
            else Serializer.from_func(
                serializer_or_func,
                match_source_subtype=match_source_subtype,
                match_target_subtype=match_target_subtype,
            )
        )
        self._register_converter(serializer)


def serialize_to_list(obj: ValueCollectionType, frame: SerializationFrame) -> list:
    """
    Serialize to list with optional sorting.
    """
    obj_list = convert_to_list(obj, frame)

    if isinstance(obj, (set, frozenset)) and frame.params.sort_sets:
        for o in obj_list:
            if not isinstance(o, SupportsComparison):
                raise ValueError(
                    f"Object '{o}' does not support comparison, so containing set cannot be converted to a sorted list"
                )
        return sorted(cast(list[SupportsComparison], obj_list))
    else:
        return obj_list

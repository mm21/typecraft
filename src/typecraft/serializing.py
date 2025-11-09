"""
Serialization capability.
"""

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

from .converting import (
    BaseConversionEngine,
    BaseConversionFrame,
    BaseConverter,
    BaseConverterRegistry,
    ConverterFuncMixin,
    ConverterFuncType,
    convert_to_list,
    normalize_to_registry,
)
from .inspecting.annotations import Annotation
from .typedefs import ValueCollectionType

__all__ = [
    "SerializerFuncType",
    "SerializationParams",
    "SerializationFrame",
    "SerializationEngine",
    "BaseSerializer",
    "Serializer",
    "SerializerRegistry",
    "serialize",
]

type JsonSerializableType = str | int | float | bool | NoneType | list[
    JsonSerializableType
] | dict[str | int | float | bool, JsonSerializableType]

JSON_SERIALIZABLE_ANNOTATION = Annotation(JsonSerializableType)

type SerializerFuncType[SourceT] = ConverterFuncType[SourceT, Any, SerializationFrame]
"""
Function which serializes the given object from a specific source type and generally
returns an object of built-in Python type. Can optionally take
`SerializationFrame` as the second argument.
"""


@dataclass(kw_only=True)
class SerializationParams:
    """
    Serialization params as passed by user.
    """

    sort_sets: bool
    """
    Whether to sort sets, produces deterministic output.
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
        context: Any | None = None,
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


class Serializer[SourceT, TargetT](
    ConverterFuncMixin[SourceT, TargetT, SerializationFrame],
    BaseSerializer[SourceT, TargetT],
):
    """
    Type-based serializer with type inference from functions.
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
        func: SerializerFuncType,
        /,
        *,
        match_source_subtype: bool = True,
        match_target_subtype: bool = False,
    ): ...

    def register(
        self,
        serializer_or_func: BaseSerializer | SerializerFuncType,
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


class SerializationEngine(BaseConversionEngine[SerializerRegistry, SerializationFrame]):
    """
    Orchestrates serialization process. Not exposed to user.
    """

    def _get_builtin_registries(
        self, frame: SerializationFrame
    ) -> tuple[SerializerRegistry, ...]:
        _ = frame
        return (JSON_REGISTRY,)


@overload
def serialize(
    obj: Any,
    /,
    *serializers: Serializer[Any, Any],
    context: Any = None,
    sort_sets: bool = True,
    source_type: Annotation | Any | None = None,
) -> JsonSerializableType: ...


@overload
def serialize(
    obj: Any,
    registry: SerializerRegistry,
    /,
    *,
    context: Any = None,
    sort_sets: bool = True,
    source_type: Annotation | Any | None = None,
) -> JsonSerializableType: ...


def serialize(
    obj: Any,
    /,
    *serializers_or_registry: Serializer[Any, Any] | SerializerRegistry,
    context: Any = None,
    sort_sets: bool = True,
    source_type: Annotation | Any | None = None,
) -> JsonSerializableType:
    """
    Recursively serialize object by type, generally to built-in Python types.

    Handles nested parameterized types by recursively applying serialization
    at each level based on the actual object types (or optionally specified source type).

    :param obj: Object to serialize
    :param context: User-defined context passed to serializers
    :param sort_sets: Whether to sort sets for deterministic output
    :param source_type: Optional source type annotation for type-specific \
    serialization; if `None`, type is inferred from the object
    """
    source_annotation = (
        Annotation._normalize(source_type)
        if source_type is not None
        else Annotation(type(obj))
    )
    registry = normalize_to_registry(
        Serializer, SerializerRegistry, *serializers_or_registry
    )
    engine = SerializationEngine(registry=registry)
    params = SerializationParams(sort_sets=sort_sets)
    frame = SerializationFrame(
        source_annotation=source_annotation,
        target_annotation=JSON_SERIALIZABLE_ANNOTATION,
        context=context,
        params=params,
        engine=engine,
    )
    return engine.process(obj, frame)


_T_contra = TypeVar("_T_contra", contravariant=True)


# technically only one of __lt__/__gt__ is required
@runtime_checkable
class SupportsComparison(Protocol[_T_contra]):
    def __lt__(self, other: _T_contra, /) -> bool: ...
    def __gt__(self, other: _T_contra, /) -> bool: ...


def _serialize_list(obj: ValueCollectionType, frame: SerializationFrame) -> list:
    obj_list = convert_to_list(
        obj, frame, default_target_annotation=JSON_SERIALIZABLE_ANNOTATION
    )

    if isinstance(obj, (set, frozenset)) and frame.params.sort_sets:
        for o in obj_list:
            if not isinstance(o, SupportsComparison):
                raise ValueError(
                    f"Object '{o}' does not support comparison, so containing set cannot be converted to a sorted list"
                )
        return sorted(cast(list[SupportsComparison], obj_list))
    else:
        return obj_list


# TODO: add more serializers: dataclasses, ...
JSON_REGISTRY = SerializerRegistry(
    Serializer(set | frozenset | tuple, list, func=_serialize_list),
)
"""
Registry to use for json serialization.
"""

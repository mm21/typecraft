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
    FuncConverterMixin,
    FuncConverterType,
    GenericConverterMixin,
    convert_to_list,
)
from .inspecting.annotations import Annotation
from .typedefs import ValueCollectionType

__all__ = [
    "FuncSerializerType",
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

type FuncSerializerType[SourceT] = FuncConverterType[SourceT, Any, SerializationFrame]
"""
Function which serializes the given object from a specific source type and generally
returns an object of built-in Python type. Can optionally take
`SerializationFrame` as the second argument.
"""


@dataclass(kw_only=True)
class SerializationParams:
    """
    Serialization params passed by user.
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
    GenericConverterMixin,
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


class SerializationEngine(BaseConversionEngine[SerializerRegistry, SerializationFrame]):
    """
    Orchestrates serialization process. Not exposed to user.
    """

    def _get_builtin_registries(
        self, frame: SerializationFrame
    ) -> tuple[SerializerRegistry, ...]:
        _ = frame
        return (JSON_REGISTRY,)


def serialize(
    obj: Any,
    /,
    *serializers: Serializer[Any, Any],
    registry: SerializerRegistry | None = None,
    params: SerializationParams | None = None,
    context: Any | None = None,
    source_type: Annotation | Any | None = None,
) -> JsonSerializableType:
    """
    Recursively serialize object by type to JSON-serializable types. Builtin types like
    `date`, `tuple`, and `set` are converted with behavior configured by `params`.

    Handles nested parameterized types like `list[list[int]]` by recursively applying
    serialization at each level based on the actual object types (or optionally
    specified source type).
    
    Specifying the source type may be useful to match a custom serializer, e.g.
    specifying `tuple[int, str]` would match a serializer with that source type
    whereas the source type would be considered as `tuple[Any, ...]` otherwise.

    :param obj: Object to serialize
    :param serializers: Custom type-based serializers
    :param registry: Registry of custom type-based serializers
    :param params:  Parameters to configure serialization behavior
    :param context: User-defined context passed to serializers
    :param source_type: Optional source type annotation for type-specific \
    serialization; if `None`, type is inferred from the object
    """
    engine = SerializationEngine._setup(converters=serializers, registry=registry)
    frame = SerializationFrame._setup(
        obj=obj,
        source_type=source_type,
        target_type=JSON_SERIALIZABLE_ANNOTATION,
        params=params,
        default_params=DEFAULT_PARAMS,
        context=context,
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


DEFAULT_PARAMS = SerializationParams()

# TODO: add more serializers: dataclasses, ...
JSON_REGISTRY = SerializerRegistry(
    Serializer(set | frozenset | tuple, list, func=_serialize_list),
)
"""
Registry to use for json serialization.
"""

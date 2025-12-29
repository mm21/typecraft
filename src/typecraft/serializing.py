"""
Serialization capability.
"""

from __future__ import annotations

from typing import (
    Any,
)

from .converting.builtin_converters import get_builtin_serializer_registry
from .converting.engine import BaseConversionEngine
from .converting.serializer import (
    JSON_SERIALIZABLE_ANNOTATION,
    BaseGenericTypeSerializer,
    BaseTypeSerializer,
    FuncSerializerType,
    JsonSerializableType,
    SerializationFrame,
    SerializationParams,
    TypeSerializer,
    TypeSerializerRegistry,
)
from .exceptions import SerializationError
from .inspecting.annotations import Annotation

__all__ = [
    "JsonSerializableType",
    "FuncSerializerType",
    "SerializationParams",
    "SerializationFrame",
    "BaseTypeSerializer",
    "BaseGenericTypeSerializer",
    "TypeSerializer",
    "TypeSerializerRegistry",
    "serialize",
]


class SerializationEngine(
    BaseConversionEngine[
        TypeSerializerRegistry,
        BaseTypeSerializer,
        SerializationFrame,
        SerializationParams,
        SerializationError,
    ]
):
    """
    Orchestrates serialization process.

    Not exposed to user.
    """

    def _get_builtin_registries(
        self, frame: SerializationFrame
    ) -> tuple[TypeSerializerRegistry, ...]:
        _ = frame
        return (
            (get_builtin_serializer_registry(),)
            if frame.params.use_builtin_serializers
            else ()
        )


def serialize(
    obj: Any,
    /,
    *serializers: BaseTypeSerializer[Any, Any],
    registry: TypeSerializerRegistry | None = None,
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
    :raises ConversionError: If any conversion errors are encountered
    """
    source_annotation = (
        Annotation._normalize(source_type) if source_type else Annotation(type(obj))
    )
    engine = SerializationEngine(converters=serializers, registry=registry)
    frame = engine.create_frame(
        source_annotation=source_annotation,
        target_annotation=JSON_SERIALIZABLE_ANNOTATION,
        params=params,
        context=context,
    )
    return engine.invoke_process(obj, frame)

"""
Serialization capability.
"""

from __future__ import annotations

from typing import (
    Any,
)

from .converting.builtin_converters import BUILTIN_SERIALIZERS
from .converting.engine import BaseConversionEngine
from .converting.serializer import (
    JSON_SERIALIZABLE_ANNOTATION,
    BaseGenericSerializer,
    BaseSerializer,
    FuncSerializerType,
    JsonSerializableType,
    SerializationFrame,
    SerializationParams,
    Serializer,
    SerializerRegistry,
    serialize_to_list,
)
from .inspecting.annotations import Annotation

__all__ = [
    "JsonSerializableType",
    "FuncSerializerType",
    "SerializationParams",
    "SerializationFrame",
    "BaseSerializer",
    "BaseGenericSerializer",
    "Serializer",
    "SerializerRegistry",
    "serialize",
]


DEFAULT_PARAMS = SerializationParams()

BUILTIN_REGISTRY = SerializerRegistry(
    Serializer(set | frozenset | tuple, list, func=serialize_to_list),
    *BUILTIN_SERIALIZERS,
)
"""
Registry to use for json serialization.
"""


class SerializationEngine(BaseConversionEngine[SerializerRegistry, SerializationFrame]):
    """
    Orchestrates serialization process. Not exposed to user.
    """

    def _get_builtin_registries(
        self, frame: SerializationFrame
    ) -> tuple[SerializerRegistry, ...]:
        _ = frame
        return (BUILTIN_REGISTRY,) if frame.params.use_builtin_serializers else ()


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

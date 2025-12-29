"""
Mechanism for bidirectional type-based conversion (validation and serialization).
"""

from __future__ import annotations

from typing import Any, overload

from .converting.serializer import JSON_SERIALIZABLE_ANNOTATION
from .inspecting.annotations import Annotation
from .serializing import (
    JsonSerializableType,
    SerializationEngine,
    SerializationParams,
    TypeSerializerRegistry,
)
from .validating import (
    TypeValidatorRegistry,
    ValidationEngine,
    ValidationParams,
)

__all__ = [
    "Adapter",
]


class Adapter[T]:
    """
    Bidirectional converter for type-based validation and serialization.

    Provides a convenient interface similar to Pydantic's `TypeAdapter` for
    validating objects to a target type and serializing objects from that type.
    """

    __annotation: Annotation
    __validation_engine: ValidationEngine
    __serialization_engine: SerializationEngine

    @overload
    def __init__(
        self,
        annotation: type[T],
        /,
        *,
        validator_registry: TypeValidatorRegistry | None = None,
        serializer_registry: TypeSerializerRegistry | None = None,
    ): ...

    @overload
    def __init__(
        self,
        annotation: Annotation | Any,
        /,
        *,
        validator_registry: TypeValidatorRegistry | None = None,
        serializer_registry: TypeSerializerRegistry | None = None,
    ): ...

    def __init__(
        self,
        annotation: type[T] | Annotation | Any,
        /,
        *,
        validator_registry: TypeValidatorRegistry | None = None,
        serializer_registry: TypeSerializerRegistry | None = None,
    ):
        self.__annotation = Annotation._normalize(annotation)
        self.__validation_engine = ValidationEngine(registry=validator_registry)
        self.__serialization_engine = SerializationEngine(registry=serializer_registry)

    def validate(
        self,
        obj: Any,
        *,
        params: ValidationParams | None = None,
        context: Any | None = None,
    ) -> T:
        """
        Validate an object to the validated type.

        :param obj: Object to validate
        :param params: Validation params
        :param context: User-defined context passed to validators
        :return: Validated object
        """
        frame = self.__validation_engine.create_frame(
            source_annotation=Annotation(type(obj)),
            target_annotation=self.__annotation,
            params=params,
            context=context,
        )
        return self.__validation_engine.invoke_process(obj, frame)

    def serialize(
        self,
        obj: T,
        *,
        params: SerializationParams | None = None,
        context: Any | None = None,
    ) -> JsonSerializableType:
        """
        Serialize an object from the validated type.

        :param obj: Object to serialize
        :param params: Serialization params
        :param context: User-defined context passed to serializers
        :return: Serialized object
        """
        frame = self.__serialization_engine.create_frame(
            source_annotation=self.__annotation,
            target_annotation=JSON_SERIALIZABLE_ANNOTATION,
            params=params,
            context=context,
        )
        return self.__serialization_engine.invoke_process(obj, frame)

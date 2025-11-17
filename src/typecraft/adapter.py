"""
Mechanism for bidirectional type-based conversion (validation and serialization).
"""

from __future__ import annotations

from typing import Any, overload

from .inspecting.annotations import Annotation
from .serializing import (
    JsonSerializableType,
    SerializationParams,
    SerializerRegistry,
    serialize,
)
from .validating import (
    ValidationParams,
    ValidatorRegistry,
    validate,
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

    _annotation: Annotation
    _validation_params: ValidationParams | None = None
    _serialization_params: SerializationParams | None = None
    _validator_registry: ValidatorRegistry | None
    _serializer_registry: SerializerRegistry | None

    @overload
    def __init__(
        self,
        annotation: type[T],
        /,
        *,
        validation_params: ValidationParams | None = None,
        serialization_params: SerializationParams | None = None,
        validator_registry: ValidatorRegistry | None = None,
        serializer_registry: SerializerRegistry | None = None,
    ): ...

    @overload
    def __init__(
        self,
        annotation: Annotation | Any,
        /,
        *,
        validation_params: ValidationParams | None = None,
        serialization_params: SerializationParams | None = None,
        validator_registry: ValidatorRegistry | None = None,
        serializer_registry: SerializerRegistry | None = None,
    ): ...

    def __init__(
        self,
        annotation: type[T] | Annotation | Any,
        /,
        *,
        validation_params: ValidationParams | None = None,
        serialization_params: SerializationParams | None = None,
        validator_registry: ValidatorRegistry | None = None,
        serializer_registry: SerializerRegistry | None = None,
    ):
        self._annotation = Annotation._normalize(annotation)
        self._validation_params = validation_params
        self._serialization_params = serialization_params
        self._validator_registry = validator_registry
        self._serializer_registry = serializer_registry

    def validate(
        self,
        obj: Any,
        *,
        context: Any | None = None,
    ) -> T:
        """
        Validate an object to the validated type.

        :param obj: Object to validate
        :param context: User-defined context passed to validators
        :return: Validated object
        """
        return validate(
            obj,
            self._annotation,
            params=self._validation_params,
            registry=self._validator_registry,
            context=context,
        )

    def serialize(
        self,
        obj: T,
        *,
        context: Any | None = None,
    ) -> JsonSerializableType:
        """
        Serialize an object from the validated type.

        :param obj: Object to serialize
        :param context: User-defined context passed to serializers
        :return: Serialized object
        """
        return serialize(
            obj,
            params=self._serialization_params,
            registry=self._serializer_registry,
            context=context,
        )

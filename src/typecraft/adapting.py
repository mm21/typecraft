"""
Adapter capability for bidirectional conversion (validation and serialization).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, overload

from .converting import extract_arg
from .inspecting.annotations import Annotation
from .serializing import (
    JsonSerializableType,
    SerializationFrame,
    SerializationParams,
    Serializer,
    SerializerRegistry,
    serialize,
)
from .validating import (
    ValidationFrame,
    ValidationParams,
    Validator,
    ValidatorRegistry,
    validate,
)

__all__ = [
    "BaseAdapter",
    "Adapter",
]


class BaseAdapter[SerializedT, ValidatedT](ABC):
    """
    Generic adapter base class for bidirectional type conversion.

    Subclass with type parameters to specify the serialized and validated types,
    then implement the abstract validation and serialization methods.
    """

    @classmethod
    def can_validate(cls, obj: SerializedT, /) -> bool:
        """
        Can be overridden by custom subclasses. Check if adapter can validate the
        given object.
        """
        _ = obj
        return True

    @classmethod
    @abstractmethod
    def validate(
        cls,
        obj: SerializedT,
        frame: ValidationFrame,
        /,
    ) -> ValidatedT:
        """
        Validate and convert from serialized to validated type.

        :param obj: Object to validate
        :param frame: Validation frame for recursion
        :return: Validated object
        """
        ...

    @classmethod
    @abstractmethod
    def serialize(
        cls,
        obj: ValidatedT,
        frame: SerializationFrame,
        /,
    ) -> SerializedT:
        """
        Serialize from validated to serialized type.

        :param obj: Object to serialize
        :param frame: Serialization frame for recursion
        :return: Serialized object
        """
        ...

    @classmethod
    def as_validator(cls) -> Validator[SerializedT, ValidatedT]:
        """
        Create a Validator from this adapter's validate method.

        :return: Validator instance configured for this adapter
        """
        source_annotation = extract_arg(cls, BaseAdapter, "SerializedT")
        target_annotation = extract_arg(cls, BaseAdapter, "ValidatedT")
        return Validator(
            source_annotation,
            target_annotation,
            func=cls.validate,
            predicate_func=cls.can_validate,
        )

    @classmethod
    def as_serializer(cls) -> Serializer[ValidatedT, SerializedT]:
        """
        Create a Serializer from this adapter's serialize method.

        :return: Serializer instance configured for this adapter
        """
        source_annotation = extract_arg(cls, BaseAdapter, "ValidatedT")
        target_annotation = extract_arg(cls, BaseAdapter, "SerializedT")
        return Serializer[ValidatedT, SerializedT](
            source_annotation,
            target_annotation,
            func=cls.serialize,
        )


class Adapter[T]:
    """
    Bidirectional converter for type-based validation and serialization.

    Provides a convenient interface similar to Pydantic's TypeAdapter for
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
        # annotation = extract_arg(type(self), TypeAdapter, "T")
        self._annotation = Annotation._normalize(annotation)
        self._validation_params = validation_params
        self._serialization_params = serialization_params
        self._validator_registry = validator_registry
        self._serializer_registry = serializer_registry

    def validate(
        self,
        obj: Any,
        *,
        context: Any = None,
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
        context: Any = None,
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

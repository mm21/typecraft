"""
Mechanism for bidirectional type-based conversion (validation and serialization).
"""

from __future__ import annotations

from typing import Any, cast, overload

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
        obj: object,
        *,
        strict: bool = False,
        use_builtin_validators: bool = True,
        by_alias: bool = False,
        context: Any = None,
    ) -> T:
        """
        Validate an object to the validated type.

        :param obj: Object to validate
        :param strict: For serializable target types, don't attempt to coerce values; just validate
        :param use_builtin_validators: For non-serializable target types, whether to use builtin validators like `str` to `date`
        :param by_alias: Whether to validate/serialize models by alias
        :param context: User-defined context passed to validators
        :return: Validated object
        """
        params = ValidationParams(
            by_alias=by_alias,
            strict=strict,
            use_builtin_validators=use_builtin_validators,
        )
        frame = self.__validation_engine.create_frame(
            source_annotation=Annotation(type(obj)),
            target_annotation=self.__annotation,
            params=params,
            context=context,
        )
        return cast(T, self.__validation_engine.invoke_process(obj, frame))

    def serialize(
        self,
        obj: T,
        *,
        sort_sets: bool = True,
        use_builtin_serializers: bool = True,
        by_alias: bool = False,
        context: Any = None,
    ) -> JsonSerializableType:
        """
        Serialize an object from the validated type.

        :param obj: Object to serialize
        :param sort_sets: Whether to sort sets, producing deterministic output
        :param use_builtin_serializers: For non-serializable types, whether to use builtin serializers like `date` to `str`
        :param by_alias: Whether to serialize models by alias
        :param context: User-defined context passed to serializers
        :return: Serialized object
        """
        params = SerializationParams(
            sort_sets=sort_sets,
            use_builtin_serializers=use_builtin_serializers,
            by_alias=by_alias,
        )
        frame = self.__serialization_engine.create_frame(
            source_annotation=self.__annotation,
            target_annotation=JSON_SERIALIZABLE_ANNOTATION,
            params=params,
            context=context,
        )
        return cast(
            JsonSerializableType, self.__serialization_engine.invoke_process(obj, frame)
        )

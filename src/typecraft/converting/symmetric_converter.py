"""
Mechanism to wrap symmetric validator and serializer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..inspecting.annotations import Annotation
from ..inspecting.generics import extract_arg
from .converter import MatchSpec
from .serializer import (
    SerializationFrame,
    Serializer,
)
from .validator import (
    ValidationFrame,
    Validator,
)

__all__ = [
    "BaseSymmetricConverter",
]


class BaseSymmetricConverter[SerializedT, ValidatedT](ABC):
    """
    Base class to encapsulate bidirectional type conversion.

    Subclass with type parameters to specify the serialized and validated types,
    then implement the abstract validation and serialization methods.
    """

    validation_match_spec: MatchSpec | None = None
    """
    Match specification for validation.
    """

    serialization_match_spec: MatchSpec | None = None
    """
    Match specification for serialization.
    """

    @classmethod
    def can_validate(cls, obj: SerializedT, /) -> bool:
        """
        Can be overridden by custom subclasses. Check if converter can validate the
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
        Create a `Validator` from this converter's `validate()` method.

        :return: Validator instance configured for this converter
        """
        source_annotation = cls.__get_serialized_annotation()
        target_annotation = cls.__get_validated_annotation()
        return Validator(
            source_annotation,
            target_annotation,
            func=cls.validate,
            predicate_func=cls.can_validate,
            match_spec=cls.validation_match_spec,
        )

    @classmethod
    def as_serializer(cls) -> Serializer[ValidatedT, SerializedT]:
        """
        Create a `Serializer` from this converter's `serialize()` method.

        :return: Serializer instance configured for this converter
        """
        source_annotation = cls.__get_validated_annotation()
        target_annotation = cls.__get_serialized_annotation()
        return Serializer[ValidatedT, SerializedT](
            source_annotation,
            target_annotation,
            func=cls.serialize,
            match_spec=cls.serialization_match_spec,
        )

    @classmethod
    def __get_serialized_annotation(cls) -> Annotation:
        return Annotation(extract_arg(cls, BaseSymmetricConverter, "SerializedT"))

    @classmethod
    def __get_validated_annotation(cls) -> Annotation:
        return Annotation(extract_arg(cls, BaseSymmetricConverter, "ValidatedT"))

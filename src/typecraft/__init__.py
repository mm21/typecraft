"""
TypeCraft: Annotation-native toolkit for data validation, transformation, and
type inspection
"""

from .exceptions import SerializationError, ValidationError
from .inspecting.annotations import Annotation, is_instance, is_narrower
from .model.base import BaseModel, ModelConfig
from .model.fields import Field
from .model.methods import (
    field_serializer,
    field_validator,
    type_serializers,
    type_validators,
)
from .serializing import serialize
from .validating import validate

__all__ = [
    # model
    "BaseModel",
    "ModelConfig",
    "Field",
    "field_validator",
    "field_serializer",
    "type_validators",
    "type_serializers",
    # core operations
    "validate",
    "serialize",
    # exceptions
    "ValidationError",
    "SerializationError",
    # annotation inspection
    "Annotation",
    "is_instance",
    "is_narrower",
]

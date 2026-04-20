"""
Dataclass-based data models with validation.

TODO:
- Implement `model_validator`, `model_serializer`
- Take field validators/serializers in annotations
"""

from .base import BaseModel, ModelConfig
from .fields import (
    Field,
    FieldInfo,
)
from .methods import (
    field_serializer,
    field_validator,
    type_serializers,
    type_validators,
)

__all__ = [
    "BaseModel",
    "ModelConfig",
    "Field",
    "FieldInfo",
    "field_serializer",
    "field_validator",
    "type_serializers",
    "type_validators",
]

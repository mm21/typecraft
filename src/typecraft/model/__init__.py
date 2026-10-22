"""
Dataclass-based data models with validation.

TODO:
- Implement `model_validator`, `model_serializer`
"""

# isort: off
# <AUTOGEN_INIT>
from .base import (
    ModelConfig,
    BaseModel,
)
from .fields import (
    Field,
    FieldMetadata,
    FieldInfo,
)
from .methods import (
    TypeValidatorsFuncType,
    TypeSerializersFuncType,
    FieldValidatorFuncType,
    FieldSerializerFuncType,
    type_validators,
    type_serializers,
    field_validator,
    field_serializer,
)

__all__ = [
    "ModelConfig",
    "BaseModel",
    "Field",
    "FieldMetadata",
    "FieldInfo",
    "TypeValidatorsFuncType",
    "TypeSerializersFuncType",
    "FieldValidatorFuncType",
    "FieldSerializerFuncType",
    "type_validators",
    "type_serializers",
    "field_validator",
    "field_serializer",
]
# </AUTOGEN_INIT>

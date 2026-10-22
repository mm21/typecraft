"""
Data conversion functionality.
"""

# isort: off
# <AUTOGEN_INIT>
from .builtin_converters import (
    DateConverter,
    DateTimeConverter,
    TimeConverter,
    DATACLASS_VALIDATOR,
    DATACLASS_SERIALIZER,
)
from .converter import (
    BaseConversionParams,
    FuncConverterWrapper,
    BaseConversionFrame,
    PlainFuncType,
    PredicateFuncType,
    BasePlainConverter,
    BaseFuncPlainConverter,
    BasePlainTransformer,
    BaseSymmetricTypeConverter,
    MatchSpec,
    BaseTypeConverter,
    BaseTypeConverterRegistry,
)
from .engine import (
    BaseConversionEngine,
)
from .mixins import (
    FuncConverterMixin,
    GenericConverterMixin,
)
from .serializer import (
    JsonSerializableType,
    FuncSerializerType,
    SerializationParams,
    SerializationFrame,
    BaseTypeSerializer,
    BaseGenericTypeSerializer,
    TypeSerializer,
    TypeSerializerRegistry,
    PlainSerializer,
)
from .utils import (
    convert_to_list,
    convert_to_tuple,
    convert_to_set,
    convert_to_dict,
    select_ann_from_union,
)
from .validator import (
    FuncValidatorType,
    ValidationParams,
    ValidationFrame,
    BaseTypeValidator,
    BaseGenericTypeValidator,
    TypeValidator,
    TypeValidatorRegistry,
    PlainValidator,
    PredicateValidator,
)

__all__ = [
    "DateConverter",
    "DateTimeConverter",
    "TimeConverter",
    "DATACLASS_VALIDATOR",
    "DATACLASS_SERIALIZER",
    "BaseConversionParams",
    "FuncConverterWrapper",
    "BaseConversionFrame",
    "PlainFuncType",
    "PredicateFuncType",
    "BasePlainConverter",
    "BaseFuncPlainConverter",
    "BasePlainTransformer",
    "BaseSymmetricTypeConverter",
    "MatchSpec",
    "BaseTypeConverter",
    "BaseTypeConverterRegistry",
    "BaseConversionEngine",
    "FuncConverterMixin",
    "GenericConverterMixin",
    "JsonSerializableType",
    "FuncSerializerType",
    "SerializationParams",
    "SerializationFrame",
    "BaseTypeSerializer",
    "BaseGenericTypeSerializer",
    "TypeSerializer",
    "TypeSerializerRegistry",
    "PlainSerializer",
    "convert_to_list",
    "convert_to_tuple",
    "convert_to_set",
    "convert_to_dict",
    "select_ann_from_union",
    "FuncValidatorType",
    "ValidationParams",
    "ValidationFrame",
    "BaseTypeValidator",
    "BaseGenericTypeValidator",
    "TypeValidator",
    "TypeValidatorRegistry",
    "PlainValidator",
    "PredicateValidator",
]
# </AUTOGEN_INIT>

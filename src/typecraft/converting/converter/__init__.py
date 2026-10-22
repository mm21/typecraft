"""
Interface for converters -- entities which perform conversion.
"""

# isort: off
# <AUTOGEN_INIT>
from .base import (
    BaseConversionParams,
    FuncConverterWrapper,
    BaseConversionFrame,
)
from .plain import (
    PlainFuncType,
    PredicateFuncType,
    BasePlainConverter,
    BaseFuncPlainConverter,
    BasePlainTransformer,
)
from .symmetric import (
    BaseSymmetricTypeConverter,
)
from .type import (
    MatchSpec,
    BaseTypeConverter,
    BaseTypeConverterRegistry,
)

__all__ = [
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
]
# </AUTOGEN_INIT>

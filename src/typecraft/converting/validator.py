from __future__ import annotations

from dataclasses import dataclass
from typing import (
    Any,
)

from .converter import (
    BaseConversionFrame,
    BaseConversionParams,
    BaseConverter,
    BaseConverterRegistry,
    FuncConverterType,
)
from .mixins import FuncConverterMixin, GenericConverterMixin

__all__ = [
    "FuncValidatorType",
    "ValidationParams",
    "ValidationFrame",
    "BaseValidator",
    "BaseGenericValidator",
    "Validator",
    "ValidatorRegistry",
]

type FuncValidatorType[TargetT] = FuncConverterType[Any, TargetT, ValidationFrame]
"""
Function which validates the given object and returns an object of the specified type.

Can optionally take `ValidationFrame` as the second argument.
"""


@dataclass(kw_only=True)
class ValidationParams(BaseConversionParams):
    """
    Validation params passed by user.
    """

    use_builtin_validators: bool = True
    """
    For non-serializable target types, whether to use builtin validators like `str` to
    `date`.
    """

    strict: bool = True
    """
    For serializable target types, don't attempt to coerce values; just validate.
    """


class ValidationFrame(BaseConversionFrame[ValidationParams]):
    """
    Internal recursion state per frame.
    """


class BaseValidator[SourceT, TargetT](BaseConverter[SourceT, TargetT, ValidationFrame]):
    """
    Base class for type-based validators.
    """


class BaseGenericValidator[SourceT, TargetT](
    GenericConverterMixin[SourceT, TargetT, ValidationFrame],
    BaseValidator[SourceT, TargetT],
):
    """
    Generic validator: subclass with type parameters to determine source/target
    type and implement `convert()`.
    """


class Validator[SourceT, TargetT](
    FuncConverterMixin[SourceT, TargetT, ValidationFrame],
    BaseValidator[SourceT, TargetT],
):
    """
    Function-based validator with optional type inference.
    """


class ValidatorRegistry(BaseConverterRegistry[BaseValidator]):
    """
    Registry for managing type-based validators.

    Provides lookup of validators based on source and target annotations.
    """

    def __repr__(self) -> str:
        return f"ValidatorRegistry(validators={self.validators})"

    @property
    def validators(self) -> list[BaseValidator]:
        """
        Get validators currently registered.
        """
        return self._converters

    def register(self, validator: BaseValidator, /):
        """
        Register a validator.
        """
        self._register_converter(validator)

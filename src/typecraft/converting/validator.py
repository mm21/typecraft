from __future__ import annotations

from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
)

from ..exceptions import ConversionErrorDetail
from ..inspecting.annotations import Annotation
from .converter import (
    BaseConversionFrame,
    BaseConversionParams,
    BaseTypeConverter,
    BaseTypeConverterRegistry,
    FuncConverterType,
)
from .mixins import FuncConverterMixin, GenericConverterMixin

if TYPE_CHECKING:
    from ..validating import ValidationEngine

__all__ = [
    "FuncValidatorType",
    "ValidationParams",
    "ValidationFrame",
    "BaseTypeValidator",
    "BaseGenericTypeValidator",
    "TypeValidator",
    "TypeValidatorRegistry",
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

    def __init__(
        self,
        *,
        source_annotation: Annotation,
        target_annotation: Annotation,
        params: ValidationParams | None,
        context: Any | None,
        engine: ValidationEngine | None = None,
        path: tuple[str | int, ...] | None = None,
        seen: set[int] | None = None,
        errors: list[ConversionErrorDetail] | None = None,
    ):
        super().__init__(
            source_annotation=source_annotation,
            target_annotation=target_annotation,
            params=params,
            context=context,
            engine=engine,
            path=path,
            seen=seen,
            errors=errors,
        )


class BaseTypeValidator[SourceT, TargetT](
    BaseTypeConverter[SourceT, TargetT, ValidationFrame]
):
    """
    Base class for type-based validators.
    """


class BaseGenericTypeValidator[SourceT, TargetT](
    GenericConverterMixin[SourceT, TargetT, ValidationFrame],
    BaseTypeValidator[SourceT, TargetT],
):
    """
    Generic validator: subclass with type parameters to determine source/target
    type and implement `convert()`.
    """


class TypeValidator[SourceT, TargetT](
    FuncConverterMixin[SourceT, TargetT, ValidationFrame],
    BaseTypeValidator[SourceT, TargetT],
):
    """
    Function-based validator with optional type inference.
    """


class TypeValidatorRegistry(BaseTypeConverterRegistry[BaseTypeValidator]):
    """
    Registry for managing type-based validators.

    Provides lookup of validators based on source and target annotations.
    """

    def __repr__(self) -> str:
        return f"ValidatorRegistry(validators={self.validators})"

    @property
    def validators(self) -> tuple[BaseTypeValidator, ...]:
        """
        Get validators currently registered.
        """
        return tuple(self._converters)

    def register(self, validator: BaseTypeValidator, /):
        """
        Register a validator.
        """
        self._register_converter(validator)

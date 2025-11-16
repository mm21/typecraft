"""
Validation capability.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import (
    Any,
    overload,
)

from .converting import (
    BaseConversionEngine,
    BaseConversionFrame,
    BaseConverter,
    BaseConverterRegistry,
    FuncConverterMixin,
    FuncConverterType,
    GenericConverterMixin,
    convert_to_dict,
    convert_to_list,
    convert_to_set,
    convert_to_tuple,
)
from .inspecting.annotations import Annotation
from .typedefs import (
    VALUE_COLLECTION_TYPES,
    ValueCollectionType,
)

__all__ = [
    "FuncValidatorType",
    "ValidationParams",
    "ValidationFrame",
    "ValidationEngine",
    "BaseGenericValidator",
    "Validator",
    "ValidatorRegistry",
    "validate",
    "normalize_to_list",
]


type FuncValidatorType[TargetT] = FuncConverterType[Any, TargetT, ValidationFrame]
"""
Function which validates the given object and returns an object of the
specified type. Can optionally take `ValidationFrame` as the second argument.
"""


@dataclass(kw_only=True)
class ValidationParams:
    """
    Validation params passed by user.
    """

    strict: bool = True
    """
    For serializable target types, don't attempt to coerce values; just validate.
    """

    use_builtins: bool = True
    """
    For non-serializable target types, use builtin converters like `str` to `date`.
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
    GenericConverterMixin,
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
    Registry for managing type validators.
    """

    def __repr__(self) -> str:
        return f"ValidatorRegistry(validators={self.validators})"

    @property
    def validators(self) -> list[BaseValidator]:
        """
        Get validators currently registered.
        """
        return self._converters

    @overload
    def register(self, validator: BaseValidator, /): ...

    @overload
    def register(
        self,
        func: FuncValidatorType,
        /,
        *,
        match_source_subtype: bool = True,
        match_target_subtype: bool = False,
    ): ...

    def register(
        self,
        validator_or_func: BaseValidator | FuncValidatorType,
        /,
        *,
        match_source_subtype: bool = True,
        match_target_subtype: bool = False,
    ):
        """
        Register a validator by `Validator` object or function.
        """
        validator = (
            validator_or_func
            if isinstance(validator_or_func, BaseValidator)
            else Validator.from_func(
                validator_or_func,
                match_source_subtype=match_source_subtype,
                match_target_subtype=match_target_subtype,
            )
        )
        self._register_converter(validator)


class ValidationEngine(BaseConversionEngine[ValidatorRegistry, ValidationFrame]):
    """
    Orchestrates validation process. Not exposed to user.
    """

    def _get_builtin_registries(
        self, frame: ValidationFrame
    ) -> tuple[ValidatorRegistry, ...]:
        return () if frame.params.strict else (BUILTIN_REGISTRY,)


@overload
def validate[T](
    obj: Any,
    target_type: type[T],
    /,
    *validators: Validator[Any, T],
    params: ValidationParams | None = None,
    context: Any = None,
) -> T: ...


@overload
def validate[T](
    obj: Any,
    target_type: type[T],
    /,
    *,
    params: ValidationParams | None = None,
    registry: ValidatorRegistry | None = None,
    context: Any = None,
) -> T: ...


@overload
def validate(
    obj: Any,
    target_type: Annotation | Any,
    /,
    *validators: Validator[Any, Any],
    params: ValidationParams | None = None,
    context: Any = None,
) -> Any: ...


@overload
def validate(
    obj: Any,
    target_type: Annotation | Any,
    /,
    *,
    params: ValidationParams | None = None,
    registry: ValidatorRegistry | None = None,
    context: Any = None,
) -> Any: ...


def validate(
    obj: Any,
    target_type: Annotation | Any,
    /,
    *validators: Validator[Any, Any],
    params: ValidationParams | None = None,
    registry: ValidatorRegistry | None = None,
    context: Any = None,
) -> Any:
    """
    Recursively validate object by type, converting to the target type if needed.

    Handles nested parameterized types like list[list[int]] by recursively
    applying validation and conversion at each level.
    """
    target_annotation = Annotation._normalize(target_type)
    registry = registry or ValidatorRegistry(*validators)
    engine = ValidationEngine(registry=registry)
    frame = ValidationFrame(
        source_annotation=Annotation(type(obj)),
        target_annotation=target_annotation,
        context=context,
        params=params or DEFAULT_PARAMS,
        engine=engine,
    )
    return engine.process(obj, frame)


# TODO: take validators_or_registry
# TODO: reuse code w/validate: engine constructor/first frame constructor, ...
def normalize_to_list[T](
    obj_or_objs: Any,
    target_type: type[T],
    /,
    *validators: Validator[Any, T],
    params: ValidationParams | None = None,
    context: Any = None,
) -> list[T]:
    """
    Validate object(s) and normalize to a list of the target type.

    Only built-in collection types and generators are expanded.
    Custom types (even if iterable) are treated as single objects.
    """
    # normalize to a collection of objects
    if isinstance(obj_or_objs, VALUE_COLLECTION_TYPES):
        objs = obj_or_objs
    else:
        objs = [obj_or_objs]

    target_annotation = Annotation._normalize(target_type)
    registry = ValidatorRegistry(*validators)
    engine = ValidationEngine(registry=registry)

    # validate each object and place in a new list
    return [
        engine.process(
            o,
            ValidationFrame(
                source_annotation=Annotation(type(o)),
                target_annotation=target_annotation,
                context=context,
                params=params or DEFAULT_PARAMS,
                engine=engine,
            ),
        )
        for o in objs
    ]


DEFAULT_PARAMS = ValidationParams()

# TODO: add more validators: dataclasses, ...
BUILTIN_REGISTRY = ValidatorRegistry(
    Validator(Any, str),
    Validator(str | bytes | bytearray, int),
    Validator(str | int, float),
    Validator(ValueCollectionType, list, func=convert_to_list),
    Validator(ValueCollectionType, tuple, func=convert_to_tuple),
    Validator(ValueCollectionType, set, func=convert_to_set),
    Validator(ValueCollectionType, frozenset, func=convert_to_set),
    Validator(Mapping, dict, func=convert_to_dict),
)
"""
Registry of built-in validators.
"""

"""
Validation capability.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import (
    Any,
    overload,
)

from .converting.builtin_converters import BUILTIN_VALIDATORS
from .converting.converter import MatchSpec
from .converting.engine import BaseConversionEngine
from .converting.utils import (
    convert_to_dict,
    convert_to_list,
    convert_to_set,
    convert_to_tuple,
)
from .converting.validator import (
    BaseGenericValidator,
    BaseValidator,
    FuncValidatorType,
    ValidationFrame,
    ValidationParams,
    Validator,
    ValidatorRegistry,
)
from .exceptions import ValidationError
from .inspecting.annotations import Annotation
from .types import VALUE_COLLECTION_TYPES, ValueCollectionType

__all__ = [
    "FuncValidatorType",
    "ValidationParams",
    "ValidationFrame",
    "BaseValidator",
    "BaseGenericValidator",
    "Validator",
    "ValidatorRegistry",
    "validate",
    "normalize_to_list",
]

DEFAULT_PARAMS = ValidationParams()

NON_STRICT_REGISTRY = ValidatorRegistry(
    Validator(str | bytes | bytearray, int),
    Validator(str | int, float),
    # set assignable_to_target=False so it doesn't match conversion to int
    Validator(Any, bool, match_spec=MatchSpec(assignable_to_target=False)),
    Validator(Any, str),
    Validator(ValueCollectionType, list, func=convert_to_list),
    Validator(ValueCollectionType, tuple, func=convert_to_tuple),
    Validator(ValueCollectionType, set, func=convert_to_set),
    Validator(ValueCollectionType, frozenset, func=convert_to_set),
    Validator(Mapping, dict, func=convert_to_dict),
)
"""
Registry of validators for non-strict mode.
"""

BUILTIN_REGISTRY = ValidatorRegistry(*BUILTIN_VALIDATORS)
"""
Registry of validators for builtin conversions.
"""


class ValidationEngine(
    BaseConversionEngine[ValidatorRegistry, ValidationFrame, ValidationError]
):
    """
    Orchestrates validation process.

    Not exposed to user.
    """

    def _get_builtin_registries(
        self, frame: ValidationFrame
    ) -> tuple[ValidatorRegistry, ...]:
        builtin_registry = (
            (BUILTIN_REGISTRY,) if frame.params.use_builtin_validators else ()
        )
        non_strict_registry = () if frame.params.strict else (NON_STRICT_REGISTRY,)
        return (*builtin_registry, *non_strict_registry)


@overload
def validate[T](
    obj: Any,
    target_type: type[T],
    /,
    *validators: Validator[Any, T],
    registry: ValidatorRegistry | None = None,
    params: ValidationParams | None = None,
    context: Any | None = None,
) -> T: ...


@overload
def validate(
    obj: Any,
    target_type: Annotation | Any,
    /,
    *validators: Validator[Any, Any],
    registry: ValidatorRegistry | None = None,
    params: ValidationParams | None = None,
    context: Any | None = None,
) -> Any: ...


def validate(
    obj: Any,
    target_type: Annotation | Any,
    /,
    *validators: Validator[Any, Any],
    registry: ValidatorRegistry | None = None,
    params: ValidationParams | None = None,
    context: Any | None = None,
) -> Any:
    """
    Recursively validate object by type, converting to the target type if configured by
    `params`.

    If both `validators` and `registry` are passed, a new registry is created with
    `validators` appended.

    Handles nested parameterized types like `list[list[int]]` by recursively
    applying validation and conversion at each level.

    :param obj: Object to validate
    :param target_type: Type to validate to
    :param validators: Custom type-based validators
    :param registry: Registry of custom type-based validators
    :param params: Parameters to configure validation behavior
    :param context: User-defined context passed to validators
    :raises ConversionError: If any conversion errors are encountered
    """
    engine = ValidationEngine._setup(converters=validators, registry=registry)
    frame = ValidationFrame._setup(
        obj=obj,
        source_type=None,
        target_type=target_type,
        params=params,
        default_params=DEFAULT_PARAMS,
        context=context,
        engine=engine,
    )
    return engine.invoke_process(obj, frame)


@overload
def normalize_to_list[T](
    obj_or_objs: Any,
    item_type: type[T],
    /,
    *validators: Validator[Any, T],
    params: ValidationParams | None = None,
    registry: ValidatorRegistry | None = None,
    context: Any | None = None,
) -> list[T]: ...


@overload
def normalize_to_list(
    obj_or_objs: Any,
    item_type: Annotation | Any,
    /,
    *validators: Validator[Any, Any],
    params: ValidationParams | None = None,
    registry: ValidatorRegistry | None = None,
    context: Any | None = None,
) -> list[Any]: ...


def normalize_to_list(
    obj_or_objs: Any,
    item_type: Annotation | Any,
    /,
    *validators: Validator[Any, Any],
    registry: ValidatorRegistry | None = None,
    params: ValidationParams | None = None,
    context: Any | None = None,
) -> list[Any]:
    """
    Validate object(s) and normalize to a list of the item type.

    Only built-in collection types and generators are expanded. Custom types (even if
    iterable) are treated as single objects.

    :raises ConversionError: If any conversion errors are encountered
    """
    objs = (
        obj_or_objs
        if isinstance(obj_or_objs, VALUE_COLLECTION_TYPES)
        else [obj_or_objs]
    )
    engine = ValidationEngine._setup(converters=validators, registry=registry)
    return [
        engine.invoke_process(
            o,
            ValidationFrame._setup(
                obj=o,
                source_type=None,
                target_type=item_type,
                params=params,
                default_params=DEFAULT_PARAMS,
                context=context,
                engine=engine,
            ),
        )
        for o in objs
    ]

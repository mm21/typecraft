"""
Validation capability.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import (
    Any,
    overload,
)

from typecraft.converting.builtin_converters import get_builtin_validator_registry

from .converting.converter.type import MatchSpec
from .converting.engine import BaseConversionEngine
from .converting.utils import (
    convert_to_dict,
    convert_to_list,
    convert_to_set,
    convert_to_tuple,
)
from .converting.validator import (
    BaseGenericTypeValidator,
    BaseTypeValidator,
    FuncValidatorType,
    TypeValidator,
    TypeValidatorRegistry,
    ValidationFrame,
    ValidationParams,
)
from .exceptions import ValidationError
from .inspecting.annotations import Annotation
from .types import VALUE_COLLECTION_TYPES, ValueCollectionType

__all__ = [
    "FuncValidatorType",
    "ValidationParams",
    "ValidationFrame",
    "BaseTypeValidator",
    "BaseGenericTypeValidator",
    "TypeValidator",
    "TypeValidatorRegistry",
    "validate",
    "normalize_to_list",
]

NON_STRICT_REGISTRY = TypeValidatorRegistry(
    TypeValidator(str | bytes | bytearray, int),
    TypeValidator(str | int, float),
    # set assignable_to_target=False so it doesn't match conversion to int
    TypeValidator(Any, bool, match_spec=MatchSpec(assignable_to_target=False)),
    TypeValidator(Any, str),
    TypeValidator(ValueCollectionType, list, func=convert_to_list),
    TypeValidator(ValueCollectionType, tuple, func=convert_to_tuple),
    TypeValidator(ValueCollectionType, set, func=convert_to_set),
    TypeValidator(ValueCollectionType, frozenset, func=convert_to_set),
    TypeValidator(Mapping, dict, func=convert_to_dict),
)
"""
Registry of validators for non-strict mode.
"""


class ValidationEngine(
    BaseConversionEngine[
        TypeValidatorRegistry,
        BaseTypeValidator,
        ValidationFrame,
        ValidationParams,
        ValidationError,
    ]
):
    """
    Orchestrates validation process.

    Not exposed to user.
    """

    def _get_builtin_registries(
        self, frame: ValidationFrame
    ) -> tuple[TypeValidatorRegistry, ...]:
        builtin_registry = (
            (get_builtin_validator_registry(),)
            if frame.params.use_builtin_validators
            else ()
        )
        non_strict_registry = () if frame.params.strict else (NON_STRICT_REGISTRY,)
        return (*builtin_registry, *non_strict_registry)


@overload
def validate[T](
    obj: Any,
    target_type: type[T],
    /,
    *validators: BaseTypeValidator[Any, T],
    registry: TypeValidatorRegistry | None = None,
    params: ValidationParams | None = None,
    context: Any | None = None,
) -> T: ...


@overload
def validate(
    obj: Any,
    target_type: Annotation | Any,
    /,
    *validators: BaseTypeValidator[Any, Any],
    registry: TypeValidatorRegistry | None = None,
    params: ValidationParams | None = None,
    context: Any | None = None,
) -> Any: ...


def validate(
    obj: Any,
    target_type: Annotation | Any,
    /,
    *validators: BaseTypeValidator[Any, Any],
    registry: TypeValidatorRegistry | None = None,
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
    engine = ValidationEngine(converters=validators, registry=registry)
    frame = engine.create_frame(
        source_annotation=Annotation(type(obj)),
        target_annotation=Annotation._normalize(target_type),
        params=params,
        context=context,
    )
    return engine.invoke_process(obj, frame)


@overload
def normalize_to_list[T](
    obj_or_objs: Any,
    item_type: type[T],
    /,
    *validators: TypeValidator[Any, T],
    params: ValidationParams | None = None,
    registry: TypeValidatorRegistry | None = None,
    context: Any | None = None,
) -> list[T]: ...


@overload
def normalize_to_list(
    obj_or_objs: Any,
    item_type: Annotation | Any,
    /,
    *validators: TypeValidator[Any, Any],
    params: ValidationParams | None = None,
    registry: TypeValidatorRegistry | None = None,
    context: Any | None = None,
) -> list[Any]: ...


def normalize_to_list(
    obj_or_objs: Any,
    item_type: Annotation | Any,
    /,
    *validators: TypeValidator[Any, Any],
    registry: TypeValidatorRegistry | None = None,
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
    target_annotation = Annotation._normalize(item_type)
    engine = ValidationEngine(converters=validators, registry=registry)
    return [
        engine.invoke_process(
            o,
            engine.create_frame(
                source_annotation=Annotation(type(o)),
                target_annotation=target_annotation,
                params=params,
                context=context,
            ),
        )
        for o in objs
    ]

"""
Validation capability.
"""

from __future__ import annotations

from typing import (
    Any,
    overload,
)

from typecraft.converting.builtin_converters import get_builtin_validator_registry

from .converting.engine import BaseConversionEngine
from .converting.validator import (
    BaseGenericTypeValidator,
    BaseTypeValidator,
    FuncValidatorType,
    PlainValidator,
    PredicateValidator,
    TypeValidator,
    TypeValidatorRegistry,
    ValidationFrame,
    ValidationParams,
)
from .exceptions import ValidationError
from .inspecting.annotations import Annotation
from .types import VALUE_COLLECTION_TYPES

__all__ = [
    "FuncValidatorType",
    "ValidationParams",
    "ValidationFrame",
    "BaseTypeValidator",
    "BaseGenericTypeValidator",
    "TypeValidator",
    "TypeValidatorRegistry",
    "PlainValidator",
    "PredicateValidator",
    "validate",
    "normalize_to_list",
]


class ValidationEngine(
    BaseConversionEngine[
        TypeValidatorRegistry,
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
        return (
            (get_builtin_validator_registry(),)
            if frame.params.use_builtin_validators
            else ()
        )


@overload
def validate[T](
    obj: object,
    target_type: type[T],
    /,
    *validators: BaseTypeValidator[Any, T],
    use_builtin_validators: bool = False,
    by_alias: bool = False,
    registry: TypeValidatorRegistry | None = None,
    context: Any = None,
) -> T: ...


@overload
def validate(
    obj: object,
    target_type: Annotation | Any,
    /,
    *validators: BaseTypeValidator[Any, Any],
    use_builtin_validators: bool = False,
    by_alias: bool = False,
    registry: TypeValidatorRegistry | None = None,
    context: Any = None,
) -> object: ...


def validate(
    obj: object,
    target_type: Annotation | Any,
    /,
    *validators: BaseTypeValidator[Any, Any],
    use_builtin_validators: bool = False,
    by_alias: bool = False,
    registry: TypeValidatorRegistry | None = None,
    context: Any = None,
) -> object:
    """
    Recursively validate object by type.

    If both `validators` and `registry` are passed, a new registry is created with
    `validators` appended.

    Handles nested parameterized types like `list[list[int]]` by recursively
    applying validation and conversion at each level.

    :param obj: Object to validate
    :param target_type: Type to validate to
    :param validators: Custom type-based validators
    :param use_builtin_validators: Whether to use builtin validators for non-serializable target types like `str` to `date`
    :param by_alias: Whether to validate/serialize models by alias
    :param registry: Registry of custom type-based validators
    :param context: User-defined context passed to validators
    :raises ConversionError: If any conversion errors are encountered
    """
    params = ValidationParams(
        by_alias=by_alias, use_builtin_validators=use_builtin_validators
    )
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
    context: Any = None,
) -> list[T]: ...


@overload
def normalize_to_list(
    obj_or_objs: Any,
    item_type: Annotation | Any,
    /,
    *validators: TypeValidator[Any, Any],
    params: ValidationParams | None = None,
    registry: TypeValidatorRegistry | None = None,
    context: Any = None,
) -> list[Any]: ...


def normalize_to_list(
    obj_or_objs: Any,
    item_type: Annotation | Any,
    /,
    *validators: TypeValidator[Any, Any],
    registry: TypeValidatorRegistry | None = None,
    params: ValidationParams | None = None,
    context: Any = None,
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

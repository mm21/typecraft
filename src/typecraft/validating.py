"""
Validation capability.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Generator,
    Union,
    cast,
    overload,
)

from .converting import (
    BaseConversionEngine,
    BaseConversionFrame,
    BaseConversionHandle,
    BaseConverterRegistry,
    BaseTypedConverter,
    ConverterFuncType,
    normalize_to_registry,
)
from .inspecting.annotations import Annotation
from .typedefs import (
    VALUE_COLLECTION_TYPES,
    ValueCollectionType,
    VarianceType,
)

__all__ = [
    "ValidatorFuncType",
    "ValidationParams",
    "ValidationHandle",
    "ValidationEngine",
    "TypedValidator",
    "ValidatorRegistry",
    "validate",
    "normalize_to_list",
]


type ValidatorFuncType[TargetT] = ConverterFuncType[Any, TargetT, ValidationHandle]
"""
Function which validates the given object and returns an object of the
specified type. Can optionally take `ValidationInfo` as the second argument.
"""


@dataclass(kw_only=True)
class ValidationParams:
    """
    Validation params as passed by user.
    """

    # TODO: rename as strict
    lenient: bool
    """
    Whether to invoke converters if object is not of correct type.
    """


class ValidationFrame(BaseConversionFrame[ValidationParams]):
    """
    Internal recursion state per frame.
    """


class ValidationHandle(BaseConversionHandle[ValidationFrame, ValidationParams]):
    """
    User-facing interface to validation state and operations.
    """

    def recurse(
        self,
        obj: Any,
        path_segment: str | int,
        target_annotation: Annotation,
        /,
        *,
        context: Any | None = None,
    ) -> Any:
        """
        Recurse into validation, overriding context if passed.
        """
        return self._frame.recurse(
            obj,
            path_segment,
            target_annotation=target_annotation,
            context=context,
        )


class TypedValidator[TargetT](BaseTypedConverter[Any, TargetT, ValidationHandle]):
    """
    Encapsulates type conversion parameters from a source annotation (which may be
    a union) to a target annotation.
    """

    @overload
    def __init__(
        self,
        source_annotation: Annotation | Any,
        target_annotation: type[TargetT],
        /,
        *,
        func: ValidatorFuncType[TargetT] | None = None,
        variance: VarianceType = "contravariant",
    ): ...

    @overload
    def __init__(
        self,
        source_annotation: Annotation | Any,
        target_annotation: Annotation | Any,
        /,
        *,
        func: ValidatorFuncType[TargetT] | None = None,
        variance: VarianceType = "contravariant",
    ): ...

    def __init__(
        self,
        source_annotation: Any,
        target_annotation: Any,
        /,
        *,
        func: ValidatorFuncType[TargetT] | None = None,
        variance: VarianceType = "contravariant",
    ):
        super().__init__(
            source_annotation, target_annotation, func=func, variance=variance
        )

    def __repr__(self) -> str:
        return f"TypedValidator(source={self._source_annotation}, target={self._target_annotation}, func={self._func_wrapper}, variance={self._variance})"

    def validate(self, obj: Any, handle: ValidationHandle, /) -> TargetT:
        """
        Convert object or raise `ValueError`.
        """

        try:
            if func := self._func_wrapper:
                # provided validation function
                validated_obj = func.invoke(obj, handle)
            else:
                # direct object construction
                concrete_type = cast(
                    Callable[[Any], TargetT], self._target_annotation.concrete_type
                )
                validated_obj = concrete_type(obj)
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"TypedValidator {self} failed to validate {obj} ({type(obj)}): {e}"
            ) from None

        if not self._target_annotation.is_type(validated_obj):
            raise ValueError(
                f"TypedValidator {self} failed to validate {obj} ({type(obj)}), got {validated_obj} ({type(validated_obj)})"
            )

        return validated_obj

    def can_convert(self, obj: Any, annotation: Annotation | Any, /) -> bool:
        """
        Check if this validator can convert the given object to the given
        target annotation.
        """
        target_ann = Annotation._normalize(annotation)

        if not self._check_variance_match(target_ann, self._target_annotation):
            return False

        return self._source_annotation.is_type(obj)


class ValidatorRegistry(BaseConverterRegistry[TypedValidator]):
    """
    Registry for managing type validators.
    """

    def __repr__(self) -> str:
        return f"ValidatorRegistry(validators={self.validators})"

    @property
    def validators(self) -> list[TypedValidator]:
        """
        Get validators currently registered.
        """
        return self._converters

    @overload
    def register(self, validator: TypedValidator[Any], /): ...

    @overload
    def register(
        self,
        func: ValidatorFuncType[Any],
        /,
        *,
        variance: VarianceType = "contravariant",
    ): ...

    def register(
        self,
        validator_or_func: TypedValidator[Any] | ValidatorFuncType[Any],
        /,
        *,
        variance: VarianceType = "contravariant",
    ):
        """
        Register a validator by `Validator` object or function.
        """
        validator = (
            validator_or_func
            if isinstance(validator_or_func, TypedValidator)
            else TypedValidator.from_func(validator_or_func, variance=variance)
        )
        self._register_converter(validator)


class ValidationEngine(BaseConversionEngine[ValidatorRegistry, ValidationFrame]):
    """
    Orchestrates validation process. Not exposed to user.
    """

    def _get_builtin_registries(
        self, frame: ValidationFrame
    ) -> tuple[ValidatorRegistry, ...]:
        return (BUILTIN_REGISTRY,) if frame.params.lenient else ()

    def _should_convert(self, obj: Any, frame: ValidationFrame) -> bool:
        """
        Check if validation conversion is needed.

        Returns True if object doesn't satisfy the target annotation.
        """
        return not _check_valid(obj, frame.target_annotation)

    def _handle_missing_converter(self, obj: Any, frame: ValidationFrame):
        if frame.params.lenient:
            # try direct object construction
            # TODO: create converter for each builtin type instead of blindly attempting
            # object construction
            return frame.target_annotation.concrete_type(obj)
        raise ValueError(
            f"Object '{obj}' ({type(obj)}) could not be converted to {frame.target_annotation}"
        )

    def _get_ref_annotation(self, obj: Any, frame: ValidationFrame) -> Annotation:
        """
        Get the target annotation for validation.
        """
        _ = obj
        return frame.target_annotation

    def _apply_converter(
        self, converter: TypedValidator, obj: Any, frame: ValidationFrame
    ) -> Any:
        """
        Apply validator to convert the object.
        """
        return converter.validate(obj, ValidationHandle(frame))

    def _convert_union(self, obj: Any, frame: ValidationFrame) -> Any:
        """
        Validate constituent types of union by trying each option.
        """
        for ann in frame.target_annotation.arg_annotations:
            try:
                return self.process(obj, frame.copy(target_annotation=ann))
            except (ValueError, TypeError):
                continue
        raise ValueError(
            f"Object '{obj}' ({type(obj)}) could not be converted to any member of union {frame.target_annotation}"
        )

    def _convert_list(
        self, obj: ValueCollectionType, frame: ValidationFrame
    ) -> list[Any]:
        """
        Validate and convert to list by recursing into items.
        """
        target_ann = frame.target_annotation
        type_ = target_ann.concrete_type
        assert issubclass(type_, list)
        assert len(target_ann.arg_annotations) == 1

        item_ann = target_ann.arg_annotations[0]
        validated_objs = [
            frame.recurse(o, i, target_annotation=item_ann) for i, o in enumerate(obj)
        ]

        if isinstance(obj, type_) and all(o is n for o, n in zip(obj, validated_objs)):
            return obj
        elif type_ is list:
            return validated_objs
        return type_(validated_objs)

    def _convert_tuple(
        self, obj: ValueCollectionType, frame: ValidationFrame
    ) -> tuple[Any]:
        """
        Validate and convert to tuple by recursing into items.
        """
        target_ann = frame.target_annotation
        type_ = target_ann.concrete_type
        assert issubclass(type_, tuple)

        if target_ann.arg_annotations[-1].raw is not ...:
            # fixed-length tuple like tuple[int, str, float]
            assert not isinstance(
                obj, set
            ), f"Can't convert from set to fixed-length tuple as items would be in random order: {obj} ({target_ann})"

            # ensure object is sized
            sized_obj = list(obj) if isinstance(obj, (range, Generator)) else obj

            if len(sized_obj) != len(target_ann.arg_annotations):
                raise ValueError(
                    f"Tuple length mismatch: expected {len(target_ann.arg_annotations)}, got {len(sized_obj)}: {sized_obj} ({target_ann})"
                )
            validated_objs = tuple(
                frame.recurse(o, i, target_annotation=item_ann)
                for i, (o, item_ann) in enumerate(
                    zip(sized_obj, target_ann.arg_annotations)
                )
            )
        else:
            # homogeneous tuple like tuple[int, ...]
            assert len(target_ann.arg_annotations) == 2
            item_ann = target_ann.arg_annotations[0]
            validated_objs = tuple(
                frame.recurse(o, i, target_annotation=item_ann)
                for i, o in enumerate(obj)
            )

        if isinstance(obj, type_) and all(o is v for o, v in zip(obj, validated_objs)):
            return obj
        elif type_ is tuple:
            return validated_objs
        return type_(validated_objs)

    def _convert_set(
        self, obj: ValueCollectionType, frame: ValidationFrame
    ) -> set[Any] | frozenset[Any]:
        """
        Validate and convert to set by recursing into items.
        """
        target_ann = frame.target_annotation
        type_ = target_ann.concrete_type
        assert issubclass(type_, (set, frozenset))
        assert len(target_ann.arg_annotations) == 1

        item_ann = target_ann.arg_annotations[0]
        validated_objs = {
            frame.recurse(o, i, target_annotation=item_ann) for i, o in enumerate(obj)
        }

        if isinstance(obj, type_):
            obj_ids = {id(o) for o in obj}
            if all(id(o) in obj_ids for o in validated_objs):
                return obj
        if type_ is set:
            return validated_objs
        return type_(validated_objs)

    def _convert_dict(self, obj: Mapping[Any, Any], frame: ValidationFrame) -> dict:
        """
        Validate and convert to dict by recursing into keys and values.
        """
        target_ann = frame.target_annotation
        type_ = target_ann.concrete_type
        assert issubclass(type_, dict)
        assert len(target_ann.arg_annotations) == 2
        key_ann, value_ann = target_ann.arg_annotations

        validated_objs = {
            frame.recurse(k, f"key[{i}]", target_annotation=key_ann): frame.recurse(
                v,
                f"[{k}]",
                target_annotation=value_ann,
            )
            for i, (k, v) in enumerate(obj.items())
        }

        if isinstance(obj, type_) and all(
            k_o is k_n and obj[k_o] is validated_objs[k_n]
            for k_o, k_n in zip(obj, validated_objs)
        ):
            return obj
        elif type_ is dict:
            return validated_objs
        return type_(**validated_objs)


@overload
def validate[T](
    obj: Any,
    target_type: type[T],
    /,
    *validators: TypedValidator[T],
    lenient: bool = False,
    context: Any = None,
) -> T: ...


@overload
def validate[T](
    obj: Any,
    target_type: type[T],
    registry: ValidatorRegistry,
    /,
    *,
    lenient: bool = False,
    context: Any = None,
) -> T: ...


@overload
def validate(
    obj: Any,
    target_type: Annotation | Any,
    /,
    *validators: TypedValidator[Any],
    lenient: bool = False,
    context: Any = None,
) -> Any: ...


@overload
def validate(
    obj: Any,
    target_type: Annotation | Any,
    registry: ValidatorRegistry,
    /,
    *,
    lenient: bool = False,
    context: Any = None,
) -> Any: ...


def validate(
    obj: Any,
    target_type: Annotation | Any,
    /,
    *validators_or_registry: TypedValidator | ValidatorRegistry,
    lenient: bool = False,
    context: Any = None,
) -> Any:
    """
    Recursively validate object by type, converting to the target type if needed.

    Handles nested parameterized types like list[list[int]] by recursively
    applying validation and conversion at each level.
    """
    target_annotation = Annotation._normalize(target_type)
    registry = normalize_to_registry(
        TypedValidator, ValidatorRegistry, *validators_or_registry
    )
    engine = ValidationEngine(registry=registry)
    params = ValidationParams(lenient=lenient)
    frame = ValidationFrame(
        source_annotation=Annotation(type(obj)),
        target_annotation=target_annotation,
        context=context,
        params=params,
        engine=engine,
    )
    return engine.process(obj, frame)


# TODO: take validators_or_registry
# TODO: reuse code w/validate: engine constructor/first frame constructor, ...
def normalize_to_list[T](
    obj_or_objs: Any,
    target_type: type[T],
    /,
    *validators: TypedValidator[T],
    lenient: bool = False,
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
    registry = normalize_to_registry(TypedValidator, ValidatorRegistry, *validators)
    engine = ValidationEngine(registry=registry)
    params = ValidationParams(lenient=lenient)

    # validate each object and place in a new list
    return [
        engine.process(
            o,
            ValidationFrame(
                source_annotation=Annotation(type(o)),
                target_annotation=target_annotation,
                context=context,
                params=params,
                engine=engine,
            ),
        )
        for o in objs
    ]


def _check_valid(obj: Any, annotation: Annotation) -> bool:
    """
    Check if object satisfies the annotation.
    """
    if annotation.is_literal:
        return obj in annotation.args
    else:
        return isinstance(obj, annotation.concrete_type)


def _validate_list(obj: ValueCollectionType, handle: ValidationHandle) -> list[Any]:
    return handle._frame.engine._convert_list(obj, handle._frame)


def _validate_tuple(obj: ValueCollectionType, handle: ValidationHandle) -> tuple[Any]:
    return handle._frame.engine._convert_tuple(obj, handle._frame)


def _validate_set(
    obj: ValueCollectionType, handle: ValidationHandle
) -> set[Any] | frozenset[Any]:
    return handle._frame.engine._convert_set(obj, handle._frame)


def _validate_dict(obj: Mapping[Any, Any], handle: ValidationHandle) -> dict[Any, Any]:
    return handle._frame.engine._convert_dict(obj, handle._frame)


BUILTIN_REGISTRY = ValidatorRegistry(
    TypedValidator(Union[VALUE_COLLECTION_TYPES], list, func=_validate_list),
    TypedValidator(Union[VALUE_COLLECTION_TYPES], tuple, func=_validate_tuple),
    TypedValidator(Union[VALUE_COLLECTION_TYPES], set, func=_validate_set),
    TypedValidator(Union[VALUE_COLLECTION_TYPES], frozenset, func=_validate_set),
    TypedValidator(Mapping, dict, func=_validate_dict),
)
"""
Registry of built-in validators.
"""

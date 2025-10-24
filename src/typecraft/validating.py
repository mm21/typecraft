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
    BaseConversionContext,
    BaseConverterRegistry,
    BaseTypedConverter,
    ConverterFunctionWrapper,
    ConverterFuncType,
    normalize_to_registry,
)
from .inspecting.annotations import Annotation
from .typedefs import (
    COLLECTION_TYPES,
    VALUE_COLLECTION_TYPES,
    CollectionType,
    ValueCollectionType,
    VarianceType,
)

__all__ = [
    "ValidatorFuncType",
    "ValidationContext",
    "TypedValidator",
    "TypedValidatorRegistry",
    "validate",
    "normalize_to_list",
]


type ValidatorFuncType[TargetT] = ConverterFuncType[Any, TargetT, ValidationInfo]
"""
Function which validates the given object and returns an object of the
specified type. Can optionally take `ValidationInfo` as the second argument.
"""


@dataclass
class ValidationInfo:
    """
    Info passed to a validation function.
    """

    target_annotation: Annotation
    context: ValidationContext


class TypedValidator[TargetT](BaseTypedConverter[Any, TargetT, ValidationInfo]):
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
        return f"TypedValidator(source={self._source_annotation}, target={self._target_annotation}, func={self._func}, variance={self._variance})"

    @classmethod
    def from_func(
        cls,
        func: ValidatorFuncType[TargetT],
        /,
        *,
        variance: VarianceType = "contravariant",
    ) -> TypedValidator[TargetT]:
        """
        Create a TypedValidator from a function by inspecting its signature.
        """
        func_wrapper = ConverterFunctionWrapper[Any, TargetT, ValidationContext](func)

        # validate sig: must take source type and return target type
        assert func_wrapper.obj_param.annotation
        assert func_wrapper.sig_info.return_annotation

        return TypedValidator(
            func_wrapper.obj_param.annotation,
            func_wrapper.sig_info.return_annotation,
            func=func,
            variance=variance,
        )

    def validate(self, obj: Any, info: ValidationInfo, /) -> TargetT:
        """
        Convert object or raise `ValueError`.

        `target_annotation` is required because some validators may inspect it
        to recurse into items of collections. For example, a validator to
        MyList[T] would invoke conversion to type T on each item.
        """

        try:
            if func := self._func:
                # provided validation function
                validated_obj = func.invoke(obj, info)
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

    def _get_context_cls(self) -> type[Any]:
        return ValidationContext


class TypedValidatorRegistry(BaseConverterRegistry[TypedValidator]):
    """
    Registry for managing type validators.

    Provides efficient lookup of validators based on source object type
    and target annotation.
    """

    def __repr__(self) -> str:
        return f"TypedValidatorRegistry(validators={self._converters})"

    @property
    def validators(self) -> list[TypedValidator]:
        """
        Get validators currently registered.
        """
        return self._converters

    def _get_map_key_type(self, converter: TypedValidator) -> type:
        """
        Get the target type to use as key in the validator map.
        """
        return converter.target_annotation.concrete_type

    @overload
    def register(self, validator: TypedValidator, /): ...

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
        Register a validator.
        """
        validator = (
            validator_or_func
            if isinstance(validator_or_func, TypedValidator)
            else TypedValidator.from_func(validator_or_func, variance=variance)
        )
        self._register_converter(validator)


class ValidationContext(BaseConversionContext[TypedValidatorRegistry]):
    """
    Encapsulates conversion parameters, propagated throughout the conversion process.
    """

    _lenient: bool

    def __init__(
        self,
        *,
        registry: TypedValidatorRegistry | None = None,
        lenient: bool = False,
    ):
        super().__init__(registry=registry)
        self._lenient = lenient

    def __repr__(self) -> str:
        return f"ValidationContext(registry={self._registry}, lenient={self._lenient})"

    def _create_default_registry(self) -> TypedValidatorRegistry:
        return TypedValidatorRegistry()

    @property
    def lenient(self) -> bool:
        return self._lenient

    @overload
    def validate[T](self, obj: Any, target_type: type[T], /) -> T: ...

    @overload
    def validate(self, obj: Any, target_type: Annotation | Any, /) -> Any: ...

    def validate(self, obj: Any, target_type: Annotation | Any, /) -> Any:
        """
        Validate object using registered typed validators.
        """
        target_annotation = Annotation._normalize(target_type)
        info = ValidationInfo(target_annotation, self)
        return _dispatch_validation(obj, info)


@overload
def validate[T](
    obj: Any,
    target_type: type[T],
    /,
    *validators: TypedValidator[T],
    lenient: bool = False,
) -> T: ...


@overload
def validate[T](
    obj: Any,
    target_type: type[T],
    registry: TypedValidatorRegistry,
    /,
    *,
    lenient: bool = False,
) -> T: ...


@overload
def validate(
    obj: Any,
    target_type: Annotation | Any,
    /,
    *validators: TypedValidator[Any],
    lenient: bool = False,
) -> Any: ...


@overload
def validate(
    obj: Any,
    target_type: Annotation | Any,
    registry: TypedValidatorRegistry,
    /,
    *,
    lenient: bool = False,
) -> Any: ...


def validate(
    obj: Any,
    target_type: Annotation | Any,
    /,
    *validators_or_registry: TypedValidator | TypedValidatorRegistry,
    lenient: bool = False,
) -> Any:
    """
    Recursively validate object by type, converting to the target type if needed.

    Handles nested parameterized types like list[list[int]] by recursively
    applying validation and conversion at each level.
    """
    registry = normalize_to_registry(
        TypedValidator, TypedValidatorRegistry, *validators_or_registry
    )
    context = ValidationContext(registry=registry, lenient=lenient)
    return context.validate(obj, target_type)


def normalize_to_list[T](
    obj_or_objs: Any,
    target_type: type[T],
    /,
    *validators: TypedValidator[T],
    lenient: bool = False,
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

    registry = normalize_to_registry(
        TypedValidator, TypedValidatorRegistry, *validators
    )
    context = ValidationContext(registry=registry, lenient=lenient)

    # validate each object and place in a new list
    return [context.validate(o, target_type) for o in objs]


def _dispatch_validation(obj: Any, info: ValidationInfo) -> Any:

    # handle union type
    if info.target_annotation.is_union:
        return _validate_union(obj, info)

    # if object does not satisfy annotation, attempt conversion
    # - validators (custom and lenient conversions) are assumed to always recurse if
    # applicable
    if not _check_valid(obj, info.target_annotation):
        return _convert(obj, info)

    # if type is a builtin collection, recurse
    if issubclass(
        info.target_annotation.concrete_type, (list, tuple, set, frozenset, dict)
    ):
        assert isinstance(obj, COLLECTION_TYPES)
        return _validate_collection(obj, info)

    # have the expected type and it's not a collection
    return obj


def _validate_union(obj: Any, info: ValidationInfo) -> Any:
    """
    Validate constituent types of union.
    """
    for arg in info.target_annotation.arg_annotations:
        try:
            return _dispatch_validation(obj, ValidationInfo(arg, info.context))
        except (ValueError, TypeError):
            continue
    raise ValueError(
        f"Object '{obj}' ({type(obj)}) could not be converted to any member of union {info.target_annotation}"
    )


def _check_valid(obj: Any, annotation: Annotation) -> bool:
    """
    Check if object satisfies the annotation.
    """
    if annotation.is_literal:
        return obj in annotation.args
    else:
        return isinstance(obj, annotation.concrete_type)


def _validate_collection(obj: CollectionType, info: ValidationInfo) -> Any:
    """
    Validate collection of objects.
    """
    ann = info.target_annotation

    assert len(
        ann.arg_annotations
    ), f"Collection annotation has no type parameter: {ann}"

    type_ = ann.concrete_type

    # handle conversion from mappings
    if issubclass(type_, dict):
        assert isinstance(obj, Mapping)
        return _validate_dict(obj, info)

    # handle conversion from value collections
    assert not isinstance(obj, Mapping)
    if issubclass(type_, list):
        return _validate_list(obj, info)
    elif issubclass(type_, tuple):
        return _validate_tuple(obj, info)
    else:
        assert issubclass(type_, (set, frozenset))
        return _validate_set(obj, info)


def _validate_list(obj: ValueCollectionType, info: ValidationInfo) -> list[Any]:
    ann, context = info.target_annotation, info.context

    type_ = ann.concrete_type
    assert issubclass(type_, list)
    assert len(ann.arg_annotations) == 1

    item_ann = ann.arg_annotations[0]
    validated_objs = [context.validate(o, item_ann) for o in obj]

    if isinstance(obj, type_) and all(o is n for o, n in zip(obj, validated_objs)):
        return obj
    elif type_ is list:
        return validated_objs
    return type_(validated_objs)


def _validate_tuple(obj: ValueCollectionType, info: ValidationInfo) -> tuple[Any]:
    ann, context = info.target_annotation, info.context

    type_ = ann.concrete_type
    assert issubclass(type_, tuple)

    if ann.arg_annotations[-1].raw is not ...:
        # fixed-length tuple like tuple[int, str, float]
        assert not isinstance(
            obj, set
        ), f"Can't convert from set to fixed-length tuple as items would be in random order: {obj} ({ann})"

        # ensure object is sized
        sized_obj = list(obj) if isinstance(obj, (range, Generator)) else obj

        if len(sized_obj) != len(ann.arg_annotations):
            raise ValueError(
                f"Tuple length mismatch: expected {len(ann.arg_annotations)}, got {len(sized_obj)}: {sized_obj} ({ann})"
            )
        validated_objs = tuple(
            context.validate(o, item_ann)
            for o, item_ann in zip(sized_obj, ann.arg_annotations)
        )
    else:
        # homogeneous tuple like tuple[int, ...]
        assert len(ann.arg_annotations) == 2
        item_ann = ann.arg_annotations[0]
        validated_objs = tuple(context.validate(o, item_ann) for o in obj)

    if isinstance(obj, type_) and all(o is v for o, v in zip(obj, validated_objs)):
        return obj
    elif type_ is tuple:
        return validated_objs
    return type_(validated_objs)


def _validate_set(
    obj: ValueCollectionType, info: ValidationInfo
) -> set[Any] | frozenset[Any]:
    ann, context = info.target_annotation, info.context

    type_ = ann.concrete_type
    assert issubclass(type_, (set, frozenset))
    assert len(ann.arg_annotations) == 1

    item_ann = ann.arg_annotations[0]
    validated_objs = {context.validate(o, item_ann) for o in obj}

    if isinstance(obj, type_):
        obj_ids = {id(o) for o in obj}
        if all(id(o) in obj_ids for o in validated_objs):
            return obj
    if type_ is set:
        return validated_objs
    return type_(validated_objs)


def _validate_dict(obj: Mapping, info: ValidationInfo) -> dict:
    ann, context = info.target_annotation, info.context

    type_ = ann.concrete_type
    assert issubclass(type_, dict)
    assert len(ann.arg_annotations) == 2
    key_ann, value_ann = ann.arg_annotations

    validated_objs = {
        context.validate(k, key_ann): context.validate(v, value_ann)
        for k, v in obj.items()
    }

    if isinstance(obj, type_) and all(
        k_o is k_n and obj[k_o] is validated_objs[k_n]
        for k_o, k_n in zip(obj, validated_objs)
    ):
        return obj
    elif type_ is dict:
        return validated_objs
    return type_(**validated_objs)


def _convert(obj: Any, info: ValidationInfo) -> Any:
    """
    Convert object by invoking validators and built-in handling, raising
    `ValueError` if it could not be converted.
    """
    # try user-provided validators from registry
    if validator := info.context.registry.find(obj, info.target_annotation):
        return validator.validate(obj, info)

    # if lenient, keep trying
    if info.context.lenient:
        # try built-in validators
        validator = BUILTIN_REGISTRY.find(obj, info.target_annotation)
        if validator:
            return validator.validate(obj, info)

        # try direct object construction
        return info.target_annotation.concrete_type(obj)

    raise ValueError(
        f"Object '{obj}' ({type(obj)}) could not be converted to {info.target_annotation}"
    )


BUILTIN_REGISTRY = TypedValidatorRegistry(
    TypedValidator(Union[VALUE_COLLECTION_TYPES], list, func=_validate_list),
    TypedValidator(Union[VALUE_COLLECTION_TYPES], tuple, func=_validate_tuple),
    TypedValidator(Union[VALUE_COLLECTION_TYPES], set, func=_validate_set),
    TypedValidator(Union[VALUE_COLLECTION_TYPES], frozenset, func=_validate_set),
    TypedValidator(Mapping, dict, func=_validate_dict),
)
"""
Registry of built-in validators.
"""

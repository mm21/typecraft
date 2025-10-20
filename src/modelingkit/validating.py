"""
Validation capability.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import (
    Any,
    Callable,
    Generator,
    Sequence,
    Union,
    cast,
    overload,
)

from .converting import ConverterFunction, normalize_to_registry
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


type ValidatorFuncType[TargetT] = Callable[[Any], TargetT] | Callable[
    [Any, Annotation], TargetT
] | Callable[[Any, ValidationContext], TargetT] | Callable[
    [Any, Annotation, ValidationContext], TargetT
]
"""
Function which validates the given object and returns an object of the
parameterized type.

Can optionally take the annotation and context, generally used to propagate to nested
objects (e.g. elements of custom collections).
"""


class TypedValidator[TargetT]:
    """
    Encapsulates type conversion parameters from a source annotation (which may be
    a union) to a target annotation.
    """

    __source_annotation: Annotation
    """
    Annotation specifying type to convert from.
    """

    __target_annotation: Annotation
    """
    Annotation specifying type to convert to.
    """

    __func: ConverterFunction | None
    """
    Function taking source type and returning an instance of target type.
    """

    __variance: VarianceType

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
        func: ValidatorFuncType[Any] | None = None,
        variance: VarianceType = "contravariant",
    ): ...

    def __init__(
        self,
        source_annotation: Any,
        target_annotation: Any,
        /,
        *,
        func: ValidatorFuncType[Any] | None = None,
        variance: VarianceType = "contravariant",
    ):
        self.__source_annotation = Annotation._normalize(source_annotation)
        self.__target_annotation = Annotation._normalize(target_annotation)
        self.__func = (
            ConverterFunction.from_func(func, ValidationContext) if func else None
        )
        self.__variance = variance

    def __repr__(self) -> str:
        return f"TypedValidator(source={self.__source_annotation}, target={self.__target_annotation}, func={self.__func}), variance={self.__variance}"

    @property
    def source_annotation(self) -> Annotation:
        return self.__source_annotation

    @property
    def target_annotation(self) -> Annotation:
        return self.__target_annotation

    @property
    def variance(self) -> VarianceType:
        return self.__variance

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
        sig = ConverterFunction.from_func(func, ValidationContext)

        # validate sig: must take source type and return target type
        assert sig.obj_param.annotation
        assert sig.sig_info.return_annotation

        return TypedValidator(
            sig.obj_param.annotation,
            sig.sig_info.return_annotation,
            func=func,
            variance=variance,
        )

    def validate(
        self,
        obj: Any,
        target_annotation: Annotation,
        context: ValidationContext,
        /,
    ) -> TargetT:
        """
        Convert object or raise `ValueError`.

        `target_annotation` is required because some validators may inspect it
        to recurse into items of collections. For example, a validator to
        MyList[T] would invoke conversion to type T on each item.
        """
        # should be checked by the caller
        assert self.can_validate(obj, target_annotation)

        try:
            if func := self.__func:
                # provided validation function
                validated_obj = func.invoke(obj, target_annotation, context)
            else:
                # direct object construction
                concrete_type = cast(
                    Callable[[Any], TargetT], self.__target_annotation.concrete_type
                )
                validated_obj = concrete_type(obj)
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"TypedValidator {self} failed to validate {obj} ({type(obj)}): {e}"
            ) from None

        if not isinstance(validated_obj, self.__target_annotation.concrete_type):
            raise ValueError(
                f"TypedValidator {self} failed to validate {obj} ({type(obj)}), got {validated_obj} ({type(validated_obj)})"
            )

        return validated_obj

    def can_validate(self, obj: Any, target_annotation: Annotation | Any, /) -> bool:
        """
        Check if this validator can convert the given object to the given
        annotation.
        """
        target_ann = Annotation._normalize(target_annotation)

        if self.__variance == "invariant":
            # exact match only
            if not target_ann == self.__target_annotation:
                return False
        else:
            # contravariant (default): annotation must be a subclass of
            # self.__target_annotation
            # - for example, a validator configured with target BaseModel can also
            # validate UserModel
            if not target_ann.is_subtype(self.__target_annotation):
                return False

        # check source
        return self.__source_annotation.is_type(obj)


class TypedValidatorRegistry:
    """
    Registry for managing type validators.

    Provides efficient lookup of validators based on source object type
    and target annotation.
    """

    __validator_map: dict[type, list[TypedValidator]]
    """
    Validators grouped by concrete target type for efficiency.
    """

    __validators: list[TypedValidator] = []
    """
    List of all validators for fallback/contravariant matching.
    """

    def __init__(self, *validators: TypedValidator):
        self.__validator_map = defaultdict(list)
        self.__validators = []
        self.extend(validators)

    def __repr__(self) -> str:
        return f"TypedValidatorRegistry(validators={self.__validators})"

    def __len__(self) -> int:
        """Return the number of registered validators."""
        return len(self.__validators)

    @property
    def validators(self) -> list[TypedValidator]:
        """
        Get validators currently registered.
        """
        return self.__validators

    @overload
    def register(self, validator: TypedValidator, /): ...

    @overload
    def register(
        self, func: ValidatorFuncType, /, *, variance: VarianceType = "contravariant"
    ): ...

    def register(
        self,
        validator_or_func: TypedValidator | ValidatorFuncType,
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
        target_type = validator.target_annotation.concrete_type
        self.__validator_map[target_type].append(validator)
        self.__validators.append(validator)

    def find(self, obj: Any, target_annotation: Annotation) -> TypedValidator | None:
        """
        Find the first validator that can handle the conversion.

        Searches in order:
        1. Exact target type matches
        2. All validators (for contravariant matching)
        """
        target_type = target_annotation.concrete_type

        # first try validators registered for the exact target type
        if target_type in self.__validator_map:
            for validator in self.__validator_map[target_type]:
                if validator.can_validate(obj, target_annotation):
                    return validator

        # then try all validators (handles contravariant, generic cases)
        for validator in self.__validators:
            if validator not in self.__validator_map.get(target_type, []):
                if validator.can_validate(obj, target_annotation):
                    return validator

        return None

    def extend(self, validators: Sequence[TypedValidator]):
        """
        Register multiple validators.
        """
        for validator in validators:
            self.register(validator)


class ValidationContext:
    """
    Encapsulates conversion parameters, propagated throughout the conversion process.
    """

    __registry: TypedValidatorRegistry
    __lenient: bool = False

    def __init__(
        self,
        *,
        registry: TypedValidatorRegistry | None = None,
        lenient: bool = False,
    ):
        self.__registry = registry or TypedValidatorRegistry()
        self.__lenient = lenient

    def __repr__(self) -> str:
        return (
            f"ValidationContext(registry={self.__registry}, lenient={self.__lenient})"
        )

    @property
    def registry(self) -> TypedValidatorRegistry:
        return self.__registry

    @property
    def lenient(self) -> bool:
        return self.__lenient

    @overload
    def validate[T](self, obj: Any, target_type: type[T], /) -> T: ...

    @overload
    def validate(self, obj: Any, target_type: Annotation | Any, /) -> Any: ...

    def validate(self, obj: Any, target_type: Annotation | Any, /) -> Any:
        """
        Validate object using registered typed validators.
        """
        target_ann = Annotation._normalize(target_type)
        return _dispatch_validation(obj, target_ann, self)


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

    # validate each object and place in a new list
    return [validate(o, target_type, *validators, lenient=lenient) for o in objs]


def _dispatch_validation(
    obj: Any,
    annotation: Annotation,
    context: ValidationContext,
) -> Any:

    # handle union type
    if annotation.is_union:
        return _validate_union(obj, annotation, context)

    # if object does not satisfy annotation, attempt conversion
    # - validators (custom and lenient conversions) are assumed to always recurse if
    # applicable
    if not _check_valid(obj, annotation):
        return _convert(obj, annotation, context)

    # if type is a builtin collection, recurse
    if issubclass(annotation.concrete_type, (list, tuple, set, frozenset, dict)):
        assert isinstance(obj, COLLECTION_TYPES)
        return _validate_collection(obj, annotation, context)

    # have the expected type and it's not a collection
    return obj


def _validate_union(
    obj: Any, annotation: Annotation, context: ValidationContext
) -> Any:
    """
    Validate constituent types of union.
    """
    for arg in annotation.arg_annotations:
        try:
            return _dispatch_validation(obj, arg, context)
        except (ValueError, TypeError):
            continue
    raise ValueError(
        f"Object '{obj}' ({type(obj)}) could not be converted to any member of union {annotation}"
    )


def _check_valid(obj: Any, annotation: Annotation) -> bool:
    """
    Check if object satisfies the annotation.
    """
    if annotation.is_literal:
        return obj in annotation.args
    else:
        return isinstance(obj, annotation.concrete_type)


def _validate_collection(
    obj: CollectionType,
    annotation: Annotation,
    context: ValidationContext,
) -> Any:
    """
    Validate collection of objects.
    """

    assert len(
        annotation.arg_annotations
    ), f"Collection annotation has no type parameter: {annotation}"

    type_ = annotation.concrete_type

    # handle conversion from mappings
    if issubclass(type_, dict):
        assert isinstance(obj, Mapping)
        return _validate_dict(obj, annotation, context)

    # handle conversion from value collections
    assert not isinstance(obj, Mapping)
    if issubclass(type_, list):
        return _validate_list(obj, annotation, context)
    elif issubclass(type_, tuple):
        return _validate_tuple(obj, annotation, context)
    else:
        assert issubclass(type_, (set, frozenset))
        return _validate_set(obj, annotation, context)


def _validate_list(
    obj: ValueCollectionType,
    annotation: Annotation,
    context: ValidationContext,
) -> list[Any]:
    type_ = annotation.concrete_type
    assert issubclass(type_, list)
    assert len(annotation.arg_annotations) == 1

    item_ann = annotation.arg_annotations[0]
    validated_objs = [context.validate(o, item_ann) for o in obj]

    if isinstance(obj, type_) and all(o is n for o, n in zip(obj, validated_objs)):
        return obj
    elif type_ is list:
        return validated_objs
    return type_(validated_objs)


def _validate_tuple(
    obj: ValueCollectionType,
    ann: Annotation,
    context: ValidationContext,
) -> tuple[Any]:
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
    obj: ValueCollectionType,
    annotation: Annotation,
    context: ValidationContext,
) -> set[Any] | frozenset[Any]:
    type_ = annotation.concrete_type
    assert issubclass(type_, (set, frozenset))
    assert len(annotation.arg_annotations) == 1

    item_ann = annotation.arg_annotations[0]
    validated_objs = {context.validate(o, item_ann) for o in obj}

    if isinstance(obj, type_):
        obj_ids = {id(o) for o in obj}
        if all(id(o) in obj_ids for o in validated_objs):
            return obj
    if type_ is set:
        return validated_objs
    return type_(validated_objs)


def _validate_dict(
    obj: Mapping,
    annotation: Annotation,
    context: ValidationContext,
) -> dict:
    type_ = annotation.concrete_type
    assert issubclass(type_, dict)
    assert len(annotation.arg_annotations) == 2
    key_ann, value_ann = annotation.arg_annotations

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


def _convert(
    obj: Any, target_annotation: Annotation, context: ValidationContext
) -> Any:
    """
    Convert object by invoking validators and built-in handling, raising
    `ValueError` if it could not be converted.
    """
    # try user-provided validators from registry
    if validator := context.registry.find(obj, target_annotation):
        return validator.validate(obj, target_annotation, context)

    # if lenient, keep trying
    if context.lenient:
        # try built-in validators
        validator = BUILTIN_REGISTRY.find(obj, target_annotation)
        if validator:
            return validator.validate(obj, target_annotation, context)

        # try direct object construction
        return target_annotation.concrete_type(obj)

    raise ValueError(
        f"Object '{obj}' ({type(obj)}) could not be converted to {target_annotation}"
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

"""
Validation capability.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
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
    BaseConverterRegistry,
    BaseTypedConverter,
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
    "ValidationEngine",
    "TypedValidator",
    "ValidatorRegistry",
    "validate",
    "normalize_to_list",
]


type ValidatorFuncType[TargetT] = ConverterFuncType[Any, TargetT, ValidationFrame]
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


@dataclass(kw_only=True)
class ValidationFrame:
    """
    Internal recursion state. A new object is created for each recursion level.
    """

    target_annotation: Annotation
    """
    Target type we're validating to.
    """

    params: ValidationParams
    """
    Parameters passed at validation entry point.
    """

    context: Any
    """
    User context passed at validation entry point.
    """

    path: tuple[str | int, ...] = field(default_factory=tuple)
    """
    Field path at this level in recursion.
    """

    seen: set[int] = field(default_factory=set)
    """
    Object ids for cycle detection.
    """

    engine: ValidationEngine
    """
    Reference to validation engine for manual recursion.
    """

    def recurse(
        self,
        obj: Any,
        annotation: Annotation,
        path_name: str | int,
        context: Any | None = None,
    ) -> Any:
        # create next frame and propagate to engine.validate()
        # TODO
        ...


class ValidationHandle:
    """
    User-facing interface to state and operations, passed to custom `validate()`
    functions.
    """

    __target_annotation: Annotation
    __params: ValidationParams
    __context: Any
    __frame: ValidationFrame

    def __init__(
        self,
        target_annotation: Annotation,
        params: ValidationParams,
        context: Any,
        frame: ValidationFrame,
    ):
        self.__target_annotation = target_annotation
        self.__params = params
        self.__context = context
        self.__frame = frame

    @property
    def target_annotation(self) -> Annotation:
        return self.__target_annotation

    @property
    def params(self) -> ValidationParams:
        return self.__params

    @property
    def context(self) -> Any:
        return self.__context

    def recurse(
        self,
        obj: Any,
        annotation: Annotation,
        path_name: str | int,
        /,
        *,
        context: Any | None = None,
    ) -> Any:
        """
        Recurse into validation, overriding context if passed.
        """
        # dispatch to frame
        return self.__frame.recurse(obj, annotation, path_name, context)


class TypedValidator[TargetT](BaseTypedConverter[Any, TargetT, ValidationFrame]):
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

    def validate(self, obj: Any, info: ValidationFrame, /) -> TargetT:
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


class ValidationEngine(BaseConversionEngine[ValidatorRegistry, ValidationParams]):
    """
    Orchestrates validation process. Not exposed to user.
    """

    def validate(self, obj: Any, frame: ValidationFrame) -> Any:
        """
        Validate object using registered typed validators.
        """
        return self._dispatch_validation(obj, frame)

    def _dispatch_validation(self, obj: Any, frame: ValidationFrame) -> Any:

        # handle union type
        if frame.target_annotation.is_union:
            return self._validate_union(obj, frame)

        # if object does not satisfy annotation, attempt conversion
        # - validators (custom and lenient conversions) are assumed to always recurse if
        # applicable
        if not _check_valid(obj, frame.target_annotation):
            return self._convert(obj, frame)

        # if type is a builtin collection, recurse
        if issubclass(
            frame.target_annotation.concrete_type, (list, tuple, set, frozenset, dict)
        ):
            assert isinstance(obj, COLLECTION_TYPES)
            return self._validate_collection(obj, frame)

        # have the expected type and it's not a collection
        return obj

    def _validate_union(self, obj: Any, frame: ValidationFrame) -> Any:
        """
        Validate constituent types of union.
        """
        for annotation in frame.target_annotation.arg_annotations:
            try:
                return self._dispatch_validation(obj, frame.with_annotation(annotation))
            except (ValueError, TypeError):
                continue
        raise ValueError(
            f"Object '{obj}' ({type(obj)}) could not be converted to any member of union {frame.target_annotation}"
        )

    def _convert(self, obj: Any, info: ValidationFrame) -> Any:
        """
        Convert object by invoking validators and built-in handling, raising
        `ValueError` if it could not be converted.
        """
        # try user-provided validators from registry
        if validator := self.registry.find(obj, info.target_annotation):
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

    def _validate_collection(self, obj: CollectionType, frame: ValidationFrame) -> Any:
        """
        Validate collection of objects.
        """
        ann = frame.target_annotation

        assert len(
            ann.arg_annotations
        ), f"Collection annotation has no type parameter: {ann}"

        type_ = ann.concrete_type

        # handle conversion from mappings
        if issubclass(type_, dict):
            assert isinstance(obj, Mapping)
            return self._validate_dict(obj, frame)

        # handle conversion from value collections
        assert not isinstance(obj, Mapping)
        if issubclass(type_, list):
            return self._validate_list(obj, frame)
        elif issubclass(type_, tuple):
            return self._validate_tuple(obj, frame)
        else:
            assert issubclass(type_, (set, frozenset))
            return self._validate_set(obj, frame)

    # TODO: reference _validate_list
    def _validate_dict(self, obj: Mapping, frame: ValidationFrame) -> dict:
        ann, engine = frame.target_annotation, frame.engine

        type_ = ann.concrete_type
        assert issubclass(type_, dict)
        assert len(ann.arg_annotations) == 2
        key_ann, value_ann = ann.arg_annotations

        validated_objs = {
            engine.validate(k, key_ann, frame): engine.validate(v, value_ann, frame)
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

    def _validate_list(
        self, obj: ValueCollectionType, frame: ValidationFrame
    ) -> list[Any]:
        ann = frame.target_annotation
        type_ = ann.concrete_type
        assert issubclass(type_, list)
        assert len(ann.arg_annotations) == 1

        item_ann = ann.arg_annotations[0]
        validated_objs = [frame.recurse(o, item_ann, i) for i, o in enumerate(obj)]

        if isinstance(obj, type_) and all(o is n for o, n in zip(obj, validated_objs)):
            return obj
        elif type_ is list:
            return validated_objs
        return type_(validated_objs)

    # TODO: reference _validate_list
    def _validate_tuple(
        self, obj: ValueCollectionType, frame: ValidationFrame
    ) -> tuple[Any]:
        ann, engine = frame.target_annotation, frame.engine

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
                engine.validate(o, item_ann, frame)
                for o, item_ann in zip(sized_obj, ann.arg_annotations)
            )
        else:
            # homogeneous tuple like tuple[int, ...]
            assert len(ann.arg_annotations) == 2
            item_ann = ann.arg_annotations[0]
            validated_objs = tuple(engine.validate(o, item_ann, frame) for o in obj)

        if isinstance(obj, type_) and all(o is v for o, v in zip(obj, validated_objs)):
            return obj
        elif type_ is tuple:
            return validated_objs
        return type_(validated_objs)

    def _validate_set(
        self, obj: ValueCollectionType, frame: ValidationFrame
    ) -> set[Any] | frozenset[Any]:
        ann, engine = frame.target_annotation, frame.engine

        type_ = ann.concrete_type
        assert issubclass(type_, (set, frozenset))
        assert len(ann.arg_annotations) == 1

        item_ann = ann.arg_annotations[0]
        validated_objs = {engine.validate(o, item_ann, frame) for o in obj}

        if isinstance(obj, type_):
            obj_ids = {id(o) for o in obj}
            if all(id(o) in obj_ids for o in validated_objs):
                return obj
        if type_ is set:
            return validated_objs
        return type_(validated_objs)


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

    # create first frame
    frame = ValidationFrame(
        target_annotation=target_annotation,
        params=params,
        context=context,
        path=(),
        seen=set(),
        engine=engine,
    )

    return engine.validate(obj, frame)


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

    # create first frame
    frame = ValidationFrame(
        target_annotation=target_annotation,
        params=params,
        context=context,
        path=(),
        seen=set(),
        engine=engine,
    )

    # validate each object and place in a new list
    return [engine.validate(o, frame) for o in objs]


def _check_valid(obj: Any, annotation: Annotation) -> bool:
    """
    Check if object satisfies the annotation.
    """
    if annotation.is_literal:
        return obj in annotation.args
    else:
        return isinstance(obj, annotation.concrete_type)


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

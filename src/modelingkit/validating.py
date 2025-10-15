"""
Validation capability.
"""

from __future__ import annotations

import inspect
from collections import defaultdict
from collections.abc import Mapping
from typing import (
    Any,
    Callable,
    Generator,
    Sequence,
    Union,
    cast,
    get_type_hints,
    overload,
)

from .converting import (
    COLLECTION_TYPES,
    VALUE_COLLECTION_TYPES,
    CollectionType,
    ValueCollectionType,
    VarianceType,
)
from .inspecting import Annotation

__all__ = [
    "ValidatorFuncType",
    "ValidationContext",
    "TypedValidator",
    "TypedValidatorRegistry",
    "validate",
    "normalize_to_list",
]


type ValidatorFuncType[T] = Callable[[Any], T] | Callable[
    [Any, Annotation, ValidationContext], T
]
"""
Function which validates the given object and returns an object of the
parameterized type. Can optionally take the annotation and context, generally
used to propagate to nested objects (e.g. elements of custom collections).
"""


class TypedValidator[T]:
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

    __func: ValidatorFuncType[Any] | None
    """
    Callable returning an instance of target type. Must take exactly one
    positional argument of the type given in `source_annotation`. May be the
    target type itself if its constructor takes exactly one positional argument.
    """

    __variance: VarianceType

    @overload
    def __init__(
        self,
        source_annotation: Any,
        target_annotation: type[T],
        /,
        *,
        func: ValidatorFuncType[T] | None = None,
        variance: VarianceType = "contravariant",
    ): ...

    @overload
    def __init__(
        self,
        source_annotation: Any,
        target_annotation: Any,
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
        self.__source_annotation = Annotation(source_annotation)
        self.__target_annotation = Annotation(target_annotation)
        self.__func = func
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

    def convert(
        self,
        obj: Any,
        target_annotation: Annotation,
        context: ValidationContext,
        /,
    ) -> T:
        """
        Convert object or raise `ValueError`.

        `target_annotation` is required because some validators may inspect it
        to recurse into items of collections. For example, a converter to
        MyList[T] would invoke conversion to type T on each item.
        """
        # should be checked by the caller
        assert self.can_convert(obj, target_annotation)

        try:
            if self.__func:
                # provided convert function
                sig = inspect.signature(self.__func)
                if len(sig.parameters) == 1:
                    # function taking object only
                    func = cast(Callable[[Any], Any], self.__func)
                    new_obj = func(obj)
                else:
                    # function taking object, annotation, context
                    func = cast(
                        Callable[[Any, Annotation, ValidationContext], Any], self.__func
                    )
                    new_obj = func(obj, target_annotation, context)
            else:
                # direct object construction
                concrete_type = cast(
                    Callable[[Any], T], self.__target_annotation.concrete_type
                )
                new_obj = concrete_type(obj)
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"TypedValidator {self} failed to convert {obj} ({type(obj)}): {e}"
            ) from None

        if not isinstance(new_obj, self.__target_annotation.concrete_type):
            raise ValueError(
                f"TypedValidator {self} failed to convert {obj} ({type(obj)}), got {new_obj} ({type(new_obj)})"
            )

        return new_obj

    def can_convert(self, obj: Any, target_annotation: Any | Annotation, /) -> bool:
        """
        Check if this converter can convert the given object to the given annotation.
        """
        target_ann = (
            target_annotation
            if isinstance(target_annotation, Annotation)
            else Annotation(target_annotation)
        )

        if self.__variance == "invariant":
            # exact match only
            if not target_ann == self.__target_annotation:
                return False
        else:
            # contravariant (default): annotation must be a subclass of
            # self.__target_annotation
            # - for example, a converter configured with target BaseModel can also
            # convert UserModel
            if not target_ann.is_subclass(self.__target_annotation):
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
    Converters grouped by concrete target type for efficiency.
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

    def add(self, converter: TypedValidator):
        """
        Add a converter to the registry.
        """
        target_type = converter.target_annotation.concrete_type
        self.__validator_map[target_type].append(converter)
        self.__validators.append(converter)

    def find(self, obj: Any, target_annotation: Annotation) -> TypedValidator | None:
        """
        Find the first converter that can handle the conversion.

        Searches in order:
        1. Exact target type matches
        2. All validators (for contravariant matching)
        """
        target_type = target_annotation.concrete_type

        # first try validators registered for the exact target type
        if target_type in self.__validator_map:
            for converter in self.__validator_map[target_type]:
                if converter.can_convert(obj, target_annotation):
                    return converter

        # then try all validators (handles contravariant, generic cases)
        for converter in self.__validators:
            if converter not in self.__validator_map.get(target_type, []):
                if converter.can_convert(obj, target_annotation):
                    return converter

        return None

    def extend(self, validators: Sequence[TypedValidator]):
        """
        Add multiple validators to the registry.
        """
        for converter in validators:
            self.add(converter)

    @overload
    def register[T](self, func: ValidatorFuncType[T]) -> ValidatorFuncType[T]: ...

    @overload
    def register[T](
        self, *, variance: VarianceType = "contravariant"
    ) -> Callable[[ValidatorFuncType[T]], ValidatorFuncType[T]]: ...

    def register[T](
        self,
        func: ValidatorFuncType[T] | None = None,
        *,
        variance: VarianceType = "contravariant",
    ) -> ValidatorFuncType | Callable[[ValidatorFuncType[T]], ValidatorFuncType[T]]:
        """
        Decorator to register a conversion function.

        Annotations are inferred from the function signature:

        ```python
        @registry.register
        def str_to_int(s: str) -> int:
            return int(s)
        ```

        Or with custom variance: (invariant means subclasses of `MyClass` will not be
        included when matching for conversion)

        ```python
        @registry.register(variance="invariant")
        def convert_exact(s: str) -> MyClass:
            return MyClass(s)
        ```

        The function can have 1 or 3 parameters:
        - 1 parameter: `func(obj) -> target`
        - 3 parameters: `func(obj, annotation, context) -> target`
        """

        def wrapper(f: ValidatorFuncType[T]) -> ValidatorFuncType[T]:
            # get type hints to handle stringized annotations from __future__ import
            try:
                # get_type_hints resolves forward references and stringized annotations
                type_hints = get_type_hints(f)
            except (NameError, AttributeError) as e:
                raise ValueError(
                    f"Failed to resolve type hints for {f.__name__}: {e}. "
                    "Ensure all types are imported or defined."
                ) from e

            # get parameters
            sig = inspect.signature(f)
            params = list(sig.parameters.keys())

            if not params:
                raise ValueError(f"Function {f.__name__} has no parameters")

            # get source annotation from first parameter
            first_param = params[0]
            if first_param not in type_hints:
                raise ValueError(
                    f"Function {f.__name__} first parameter '{first_param}' "
                    "has no type annotation."
                )
            source_annotation = type_hints[first_param]

            # get target annotation from return type
            if "return" not in type_hints:
                raise ValueError(
                    f"Function {f.__name__} has no return type annotation."
                )
            target_annotation = type_hints["return"]

            # validate parameter count
            param_count = len(params)
            if param_count not in (1, 3):
                raise ValueError(
                    f"TypedValidator function {f.__name__} must have 1 or 3 parameters, "
                    f"got {param_count}"
                )

            # create and register the converter
            converter = TypedValidator(
                source_annotation, target_annotation, func=f, variance=variance
            )
            self.add(converter)

            return f

        # handle both @register and @register(...) syntax
        if func is None:
            # called with parameters: @register(...)
            return wrapper
        else:
            # called without parameters: @register
            return wrapper(func)


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
    def validate(self, obj: Any, target_type: Any | Annotation, /) -> Any: ...

    def validate(self, obj: Any, target_type: Any | Annotation, /) -> Any:
        """
        Validate object using registered typed validators.
        """
        target_ann = (
            target_type
            if isinstance(target_type, Annotation)
            else Annotation(target_type)
        )
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
def validate(
    obj: Any,
    target_type: Any | Annotation,
    /,
    *validators: TypedValidator[Any],
    lenient: bool = False,
) -> Any: ...


def validate(
    obj: Any,
    target_type: Any | Annotation,
    /,
    *validators: TypedValidator[Any],
    lenient: bool = False,
) -> Any:
    """
    Recursively validate object, converting to the target type if applicable.

    Handles nested parameterized types like list[list[int]] by recursively
    applying validation and conversion at each level.
    """
    context = ValidationContext(
        registry=TypedValidatorRegistry(*validators), lenient=lenient
    )
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
    if issubclass(annotation.concrete_type, (list, tuple, set, dict)):
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
    ), f"Collection has no type parameter: {obj} ({annotation})"

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
        assert issubclass(type_, set)
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

    if ann.arg_annotations[-1].annotation is not ...:
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
) -> set[Any]:
    type_ = annotation.concrete_type
    assert issubclass(type_, set)
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
    Convert object by invoking validators and built-in handling, raising `ValueError`
    if it could not be converted.
    """
    # try user-provided validators from registry
    converter = context.registry.find(obj, target_annotation)
    if converter:
        return converter.convert(obj, target_annotation, context)

    # if lenient, keep trying
    if context.lenient:
        # try built-in validators
        converter = BUILTIN_REGISTRY.find(obj, target_annotation)
        if converter:
            return converter.convert(obj, target_annotation, context)

        # try direct object construction
        return target_annotation.concrete_type(obj)

    raise ValueError(
        f"Object '{obj}' ({type(obj)}) could not be converted to {target_annotation}"
    )


BUILTIN_REGISTRY = TypedValidatorRegistry(
    TypedValidator(Union[VALUE_COLLECTION_TYPES], list, func=_validate_list),
    TypedValidator(Union[VALUE_COLLECTION_TYPES], tuple, func=_validate_tuple),
    TypedValidator(Union[VALUE_COLLECTION_TYPES], set, func=_validate_set),
    TypedValidator(Mapping, dict, func=_validate_dict),
)
"""
Registry of built-in validators.
"""

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
    def validate[T](self, obj: Any, target_type: type[T]) -> T: ...

    @overload
    def validate(self, obj: Any, target_type: Any) -> Any: ...

    def validate(self, obj: Any, target_type: Any) -> Any:
        """
        Propagate validation for given object.
        """
        return _dispatch_validation(obj, target_type, self)


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
    Callable returning an instance of target type. Must take exactly one positional
    argument of one of the type(s) given in `from_types`. May be the target type itself
    if its constructor takes exactly one positional argument.
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
        target_annotation: Any = Any,
        /,
        *,
        func: ValidatorFuncType[Any] | None = None,
        variance: VarianceType = "contravariant",
    ): ...

    def __init__(
        self,
        source_annotation: Any,
        target_annotation: Any = Any,
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
    def target_annotation(self) -> Annotation:
        return self.__target_annotation

    @property
    def source_annotation(self) -> Annotation:
        return self.__source_annotation

    @property
    def variance(self) -> VarianceType:
        return self.__variance

    # note: context is only passed for isolated testing; it should always be passed
    # in the validate()/serialize() procedures
    def convert(
        self,
        obj: Any,
        target_annotation: Annotation,
        context: ValidationContext | None = None,
        /,
    ) -> T:
        """
        Convert object or raise `ValueError`.

        `target_annotation` is required because some converters may inspect it to
        recurse into items of collections. For example, a converter to MyList[T]
        would invoke conversion to type T on each item.
        """
        # should be checked by the caller
        assert self.can_convert(obj, target_annotation)

        context_ = context or ValidationContext(registry=TypedValidatorRegistry(self))

        try:
            if self.__func:
                # provided convert function
                sig = inspect.signature(self.__func)
                if len(sig.parameters) == 1:
                    func = cast(Callable[[Any], Any], self.__func)
                    new_obj = func(obj)
                else:
                    func = cast(
                        Callable[[Any, Annotation, ValidationContext], Any], self.__func
                    )
                    new_obj = func(obj, target_annotation, context_)
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

    @overload
    def can_convert(self, obj: Any, target_annotation: Annotation, /) -> bool: ...

    @overload
    def can_convert(self, obj: Any, target_annotation: Any, /) -> bool: ...

    def can_convert(self, obj: Any, target_annotation: Any, /) -> bool:
        """
        Check if this converter can convert the given object to the given annotation.
        """
        target_annotation_ = (
            target_annotation
            if isinstance(target_annotation, Annotation)
            else Annotation(target_annotation)
        )

        if self.__variance == "invariant":
            # exact match only
            if not target_annotation_ == self.__target_annotation:
                return False
        else:
            # contravariant (default): annotation must be a subclass of
            # self.__target_annotation
            # - for example, a converter configured with target BaseModel can also
            # convert UserModel
            if not target_annotation_.is_subclass(self.__target_annotation):
                return False

        # check source
        return self.__source_annotation.is_type(obj)


class TypedValidatorRegistry:
    """
    Registry for managing type converters.

    Provides efficient lookup of converters based on source object type
    and target annotation.
    """

    __converter_map: dict[type, list[TypedValidator]]
    """
    Converters grouped by concrete target type for efficiency.
    """

    __converters: list[TypedValidator] = []
    """
    List of all converters for fallback/contravariant matching.
    """

    def __init__(self, *converters: TypedValidator):
        self.__converter_map = defaultdict(list)
        self.__converters = []
        self.extend(converters)

    def __repr__(self) -> str:
        return f"TypedValidatorRegistry(converters={self.__converters})"

    def __len__(self) -> int:
        """Return the number of registered converters."""
        return len(self.__converters)

    @property
    def converters(self) -> list[TypedValidator]:
        """
        Get converters currently registered.
        """
        return self.__converters

    def add(self, converter: TypedValidator):
        """
        Add a converter to the registry.
        """
        target_type = converter.target_annotation.concrete_type
        self.__converter_map[target_type].append(converter)
        self.__converters.append(converter)

    def find(self, obj: Any, target_annotation: Annotation) -> TypedValidator | None:
        """
        Find the first converter that can handle the conversion.

        Searches in order:
        1. Exact target type matches
        2. All converters (for contravariant matching)
        """
        target_type = target_annotation.concrete_type

        # first try converters registered for the exact target type
        if target_type in self.__converter_map:
            for converter in self.__converter_map[target_type]:
                if converter.can_convert(obj, target_annotation):
                    return converter

        # then try all converters (handles contravariant, generic cases)
        for converter in self.__converters:
            if converter not in self.__converter_map.get(target_type, []):
                if converter.can_convert(obj, target_annotation):
                    return converter

        return None

    def extend(self, converters: Sequence[TypedValidator]):
        """
        Add multiple converters to the registry.
        """
        for converter in converters:
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


@overload
def validate[T](
    obj: Any,
    target_type: type[T],
    /,
    *converters: TypedValidator[T],
    lenient: bool = False,
) -> T: ...


@overload
def validate[T](
    obj: Any,
    target_type: type[T],
    /,
    *,
    context: ValidationContext | None = None,
) -> T: ...


@overload
def validate(
    obj: Any,
    target_type: Any,
    /,
    *converters: TypedValidator[Any],
    lenient: bool = False,
) -> Any: ...


@overload
def validate(
    obj: Any,
    target_type: Any,
    /,
    *,
    context: ValidationContext | None = None,
) -> Any: ...


def validate(
    obj: Any,
    target_type: Any,
    /,
    *converters: TypedValidator[Any],
    lenient: bool = False,
    context: ValidationContext | None = None,
) -> Any:
    """
    Recursively validate object, converting to the target type if applicable.

    Handles nested parameterized types like list[list[int]] by recursively
    applying validation and conversion at each level.
    """
    # can only pass context or registry, not both
    if context:
        assert len(converters) == 0

    context_ = context or ValidationContext(
        registry=TypedValidatorRegistry(*converters), lenient=lenient
    )
    target_annotation = (
        target_type if isinstance(target_type, Annotation) else Annotation(target_type)
    )
    return _dispatch_validation(obj, target_annotation, context_)


def normalize_to_list[T](
    obj_or_objs: Any,
    target_type: type[T],
    /,
    *converters: TypedValidator[T],
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
    return [validate(o, target_type, *converters, lenient=lenient) for o in objs]


def _dispatch_validation(
    obj: Any,
    annotation_info: Annotation,
    context: ValidationContext,
) -> Any:

    # handle union type
    if annotation_info.is_union:
        return _validate_union(obj, annotation_info, context)

    # if object does not satisfy annotation, attempt conversion
    # - converters (custom and lenient conversions) are assumed to always recurse if
    # applicable
    if not _check_valid(obj, annotation_info):
        return _convert(obj, annotation_info, context)

    # if type is a builtin collection, recurse
    if issubclass(annotation_info.concrete_type, (list, tuple, set, dict)):
        assert isinstance(obj, COLLECTION_TYPES)
        return _validate_collection(obj, annotation_info, context)

    # have the expected type and it's not a collection
    return obj


def _validate_union(
    obj: Any, annotation_info: Annotation, context: ValidationContext
) -> Any:
    """
    Validate constituent types of union.
    """
    for arg in annotation_info.arg_annotations:
        try:
            return _dispatch_validation(obj, arg, context)
        except (ValueError, TypeError):
            continue
    raise ValueError(
        f"Object '{obj}' ({type(obj)}) could not be converted to any member of union {annotation_info}"
    )


def _check_valid(obj: Any, annotation_info: Annotation) -> bool:
    """
    Check if object satisfies the annotation.
    """
    if annotation_info.is_literal:
        return obj in annotation_info.args
    else:
        return isinstance(obj, annotation_info.concrete_type)


def _validate_collection(
    obj: CollectionType,
    annotation_info: Annotation,
    context: ValidationContext,
) -> Any:
    """
    Validate collection of objects.
    """

    assert len(
        annotation_info.arg_annotations
    ), f"Collection has no type parameter: {obj} ({annotation_info})"

    type_ = annotation_info.concrete_type

    # handle conversion from mappings
    if issubclass(type_, dict):
        assert isinstance(obj, Mapping)
        return _validate_dict(obj, annotation_info, context)

    # handle conversion from value collections
    assert not isinstance(obj, Mapping)
    if issubclass(type_, list):
        return _validate_list(obj, annotation_info, context)
    elif issubclass(type_, tuple):
        return _validate_tuple(obj, annotation_info, context)
    else:
        assert issubclass(type_, set)
        return _validate_set(obj, annotation_info, context)


def _validate_list(
    obj: ValueCollectionType,
    annotation_info: Annotation,
    context: ValidationContext,
) -> list[Any]:
    type_ = annotation_info.concrete_type
    assert issubclass(type_, list)
    assert len(annotation_info.arg_annotations) == 1

    item_type = annotation_info.arg_annotations[0]
    validated_objs = [validate(o, item_type, context=context) for o in obj]

    if isinstance(obj, type_) and all(o is n for o, n in zip(obj, validated_objs)):
        return obj
    elif type_ is list:
        return validated_objs
    return type_(validated_objs)


def _validate_tuple(
    obj: ValueCollectionType,
    annotation_info: Annotation,
    context: ValidationContext,
) -> tuple[Any]:
    type_ = annotation_info.concrete_type
    assert issubclass(type_, tuple)

    if annotation_info.arg_annotations[-1].annotation is not ...:
        # fixed-length tuple like tuple[int, str, float]
        assert not isinstance(
            obj, set
        ), f"Can't convert from set to fixed-length tuple as items would be in random order: {obj} ({annotation_info})"

        # ensure object is sized
        sized_obj = list(obj) if isinstance(obj, (range, Generator)) else obj

        if len(sized_obj) != len(annotation_info.arg_annotations):
            raise ValueError(
                f"Tuple length mismatch: expected {len(annotation_info.arg_annotations)}, got {len(sized_obj)}: {sized_obj} ({annotation_info})"
            )
        validated_objs = tuple(
            validate(o, item_type, context=context)
            for o, item_type in zip(sized_obj, annotation_info.arg_annotations)
        )
    else:
        # homogeneous tuple like tuple[int, ...]
        assert len(annotation_info.arg_annotations) == 2
        item_type = annotation_info.arg_annotations[0]
        validated_objs = tuple(validate(o, item_type, context=context) for o in obj)

    if isinstance(obj, type_) and all(o is n for o, n in zip(obj, validated_objs)):
        return obj
    elif type_ is tuple:
        return validated_objs
    return type_(validated_objs)


def _validate_set(
    obj: ValueCollectionType,
    annotation_info: Annotation,
    context: ValidationContext,
) -> set[Any]:
    type_ = annotation_info.concrete_type
    assert issubclass(type_, set)
    assert len(annotation_info.arg_annotations) == 1

    item_type = annotation_info.arg_annotations[0]
    validated_objs = {validate(o, item_type, context=context) for o in obj}

    if isinstance(obj, type_):
        obj_ids = {id(o) for o in obj}
        if all(id(n) in obj_ids for n in validated_objs):
            return obj
    if type_ is set:
        return validated_objs
    return type_(validated_objs)


def _validate_dict(
    obj: Mapping,
    annotation_info: Annotation,
    context: ValidationContext,
) -> dict:
    type_ = annotation_info.concrete_type
    assert issubclass(type_, dict)
    assert len(annotation_info.arg_annotations) == 2
    key_type, value_type = annotation_info.arg_annotations

    validated_objs = {
        validate(k, key_type, context=context): validate(v, value_type, context=context)
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
    Convert object by invoking converters and built-in handling, raising `ValueError`
    if it could not be converted.
    """
    # try user-provided converters from registry
    converter = context.registry.find(obj, target_annotation)
    if converter:
        return converter.convert(obj, target_annotation, context)

    # if lenient, keep trying
    if context.lenient:
        # try built-in converters
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
Registry of built-in converters.
"""

"""
Serialization capability.
"""

from __future__ import annotations

import inspect
from collections import defaultdict
from collections.abc import Mapping
from typing import (
    Any,
    Callable,
    Sequence,
    cast,
    get_type_hints,
    overload,
)

from .inspecting import Annotation
from .typedefs import (
    COLLECTION_TYPES,
    CollectionType,
    VarianceType,
)

__all__ = [
    "SerializerFuncType",
    "SerializationContext",
    "TypedSerializer",
    "TypedSerializerRegistry",
    "serialize",
]


type SerializerFuncType[T] = Callable[[T], Any] | Callable[
    [T, Annotation, SerializationContext], Any
]
"""
Function which serializes the given object and returns a 
JSON-serializable object. Can optionally take the annotation and context,
generally used to propagate to nested objects (e.g. elements of custom
collections).
"""


class TypedSerializer[T]:
    """
    Encapsulates serialization parameters from a source annotation.
    """

    __source_annotation: Annotation
    """
    Annotation specifying type to serialize from.
    """

    __func: SerializerFuncType
    """
    Callable returning a serializable object. Must take exactly one positional
    argument of the type given in `source_annotation`.
    """

    __variance: VarianceType

    @overload
    def __init__(
        self,
        source_annotation: type[T],
        /,
        *,
        func: SerializerFuncType[T],
        variance: VarianceType = "contravariant",
    ): ...

    @overload
    def __init__(
        self,
        source_annotation: Any,
        /,
        *,
        func: SerializerFuncType,
        variance: VarianceType = "contravariant",
    ): ...

    def __init__(
        self,
        source_annotation: Any,
        func: SerializerFuncType,
        variance: VarianceType = "contravariant",
    ):
        self.__source_annotation = Annotation(source_annotation)
        self.__func = func
        self.__variance = variance

    def __repr__(self) -> str:
        return f"TypedSerializer(source={self.__source_annotation}, func={self.__func}, variance={self.__variance})"

    @property
    def source_annotation(self) -> Annotation:
        return self.__source_annotation

    @property
    def variance(self) -> VarianceType:
        return self.__variance

    def serialize(
        self,
        obj: Any,
        source_annotation: Annotation,
        context: SerializationContext,
        /,
    ) -> Any:
        """
        Serialize object or raise `ValueError`.

        `source_annotation` is required because some serializers may inspect it
        to recurse into items of collections.
        """
        # should be checked by the caller
        assert self.can_serialize(obj, source_annotation)

        # attempt to get number of parameters from signature
        try:
            sig = inspect.signature(self.__func)
        except ValueError:
            # could be a builtin type, no signature available; assume it takes
            # one arg
            param_count = 1
        else:
            param_count = len(sig.parameters)

        # invoke serialization function
        try:
            if param_count == 1:
                # function taking object only
                func = cast(Callable[[Any], Any], self.__func)
                serialized = func(obj)
            else:
                # function taking object, annotation, context
                assert param_count == 3
                func = cast(
                    Callable[[Any, Annotation, SerializationContext], Any],
                    self.__func,
                )
                serialized = func(obj, source_annotation, context)
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"TypedSerializer {self} failed to serialize {obj} ({type(obj)}): {e}"
            ) from None

        return serialized

    def can_serialize(self, obj: Any, source_annotation: Any | Annotation, /) -> bool:
        """
        Check if this serializer can serialize the given object with the given
        annotation.
        """
        source_ann = Annotation._normalize(source_annotation)

        if self.__variance == "invariant":
            # exact match only
            if not source_ann == self.__source_annotation:
                return False
        else:
            # contravariant (default): annotation must be a subclass of
            # self.__source_annotation
            if not source_ann.is_subclass(self.__source_annotation):
                return False

        # check that object matches source annotation
        return source_ann.is_type(obj)


class TypedSerializerRegistry:
    """
    Registry for managing type serializers.

    Provides efficient lookup of serializers based on source object type
    and source annotation.
    """

    __serializer_map: dict[type, list[TypedSerializer]]
    """
    Serializers grouped by concrete source type for efficiency.
    """

    __serializers: list[TypedSerializer] = []
    """
    List of all serializers for fallback/contravariant matching.
    """

    def __init__(self, *serializers: TypedSerializer):
        self.__serializer_map = defaultdict(list)
        self.__serializers = []
        self.extend(serializers)

    def __repr__(self) -> str:
        return f"TypedSerializerRegistry(serializers={self.__serializers})"

    def __len__(self) -> int:
        """Return the number of registered serializers."""
        return len(self.__serializers)

    @property
    def serializers(self) -> list[TypedSerializer]:
        """
        Get serializers currently registered.
        """
        return self.__serializers

    def add(self, serializer: TypedSerializer):
        """
        Add a serializer to the registry.
        """
        source_type = serializer.source_annotation.concrete_type
        self.__serializer_map[source_type].append(serializer)
        self.__serializers.append(serializer)

    def find(self, obj: Any, source_annotation: Annotation) -> TypedSerializer | None:
        """
        Find the first serializer that can handle the serialization.

        Searches in order:
        1. Exact source type matches
        2. All serializers (for contravariant matching)
        """
        source_type = source_annotation.concrete_type

        # first try serializers registered for the exact source type
        if source_type in self.__serializer_map:
            for serializer in self.__serializer_map[source_type]:
                if serializer.can_serialize(obj, source_annotation):
                    return serializer

        # then try all serializers (handles contravariant, generic cases)
        for serializer in self.__serializers:
            if serializer not in self.__serializer_map.get(source_type, []):
                if serializer.can_serialize(obj, source_annotation):
                    return serializer

        return None

    def extend(self, serializers: Sequence[TypedSerializer]):
        """
        Add multiple serializers to the registry.
        """
        for serializer in serializers:
            self.add(serializer)

    @overload
    def register(self, func: SerializerFuncType) -> SerializerFuncType: ...

    @overload
    def register(
        self, *, variance: VarianceType = "contravariant"
    ) -> Callable[[SerializerFuncType], SerializerFuncType]: ...

    def register(
        self,
        func: SerializerFuncType | None = None,
        *,
        variance: VarianceType = "contravariant",
    ) -> SerializerFuncType | Callable[[SerializerFuncType], SerializerFuncType]:
        """
        Decorator to register a serialization function.

        Annotations are inferred from the function signature:

        ```python
        @registry.register
        def serialize_myclass(obj: MyClass) -> dict:
            return {"value": obj.value}
        ```

        Or with custom variance:

        ```python
        @registry.register(variance="invariant")
        def serialize_exact(obj: MyClass) -> dict:
            return {"value": obj.value}
        ```

        The function can have 1 or 3 parameters:
        - 1 parameter: `func(obj) -> serialized`
        - 3 parameters: `func(obj, annotation, context) -> serialized`

        Return type annotation is not required.
        """

        def wrapper(wrapped_func: SerializerFuncType) -> SerializerFuncType:
            # get type hints
            try:
                type_hints = get_type_hints(wrapped_func)
            except (NameError, AttributeError) as e:
                raise ValueError(
                    f"Failed to resolve type hints for {wrapped_func.__name__}: {e}. "
                    "Ensure all types are imported or defined."
                ) from e

            # get parameters
            sig = inspect.signature(wrapped_func)
            params = list(sig.parameters.keys())

            if not params:
                raise ValueError(f"Function {wrapped_func.__name__} has no parameters")

            # get source annotation from first parameter
            first_param = params[0]
            if first_param not in type_hints:
                raise ValueError(
                    f"Function {wrapped_func.__name__} first parameter '{first_param}' "
                    "has no type annotation."
                )
            source_annotation = type_hints[first_param]

            # validate parameter count
            param_count = len(params)
            if param_count not in (1, 3):
                raise ValueError(
                    f"TypedSerializer function {wrapped_func.__name__} must have 1 or 3 parameters, "
                    f"got {param_count}"
                )

            # create and register the serializer
            serializer = TypedSerializer(
                source_annotation, func=wrapped_func, variance=variance
            )
            self.add(serializer)

            return wrapped_func

        # handle both @register and @register(...) syntax
        if func is None:
            # called with parameters: @register(...)
            return wrapper
        else:
            # called without parameters: @register
            return wrapper(func)


class SerializationContext:
    """
    Encapsulates serialization parameters, propagated throughout the
    serialization process.
    """

    __registry: TypedSerializerRegistry

    def __init__(
        self,
        *,
        registry: TypedSerializerRegistry | None = None,
    ):
        self.__registry = registry or TypedSerializerRegistry()

    def __repr__(self) -> str:
        return f"SerializationContext(registry={self.__registry})"

    @property
    def registry(self) -> TypedSerializerRegistry:
        return self.__registry

    def serialize(
        self, obj: Any, source_type: Any | Annotation | None = None, /
    ) -> Any:
        """
        Serialize object using registered typed serializers.

        If source_type is not provided, infers annotation from object's type.
        """
        if source_type is None:
            source_ann = Annotation(type(obj))
        else:
            source_ann = Annotation._normalize(source_type)
        return _dispatch_serialization(obj, source_ann, self)


def serialize(
    obj: Any,
    source_type: Any | Annotation | None = None,
    /,
    *serializers: TypedSerializer,
) -> Any:
    """
    Recursively serialize object to a JSON-serializable format.

    Handles nested parameterized types like list[MyClass] by recursively
    applying serialization at each level.

    Args:
        obj: Object to serialize
        source_type: Optional type hint for the object (inferred from obj if not provided)
        *serializers: Custom serializers to use
    """
    context = SerializationContext(registry=TypedSerializerRegistry(*serializers))
    return context.serialize(obj, source_type)


def _dispatch_serialization(
    obj: Any,
    annotation: Annotation,
    context: SerializationContext,
) -> Any:
    """
    Main serialization dispatcher.
    """

    # handle None
    if obj is None:
        return None

    # handle union type
    if annotation.is_union:
        return _serialize_union(obj, annotation, context)

    # try user-provided serializers first (even for primitives/collections)
    if serializer := context.registry.find(obj, annotation):
        return serializer.serialize(obj, annotation, context)

    # handle builtin collections
    if isinstance(obj, COLLECTION_TYPES):
        return _serialize_collection(obj, annotation, context)

    # no serializer found, return as-is
    return obj


def _serialize_union(
    obj: Any, annotation: Annotation, context: SerializationContext
) -> Any:
    """
    Serialize union types by finding the matching constituent type.
    """
    for arg in annotation.arg_annotations:
        if arg.is_type(obj):
            return _dispatch_serialization(obj, arg, context)

    # no matching union member, serialize with inferred type
    return _dispatch_serialization(obj, Annotation(type(obj)), context)


def _serialize_collection(
    obj: CollectionType,
    annotation: Annotation,
    context: SerializationContext,
) -> Any:
    """
    Serialize collection of objects.
    """

    # handle dict
    if isinstance(obj, Mapping):
        return _serialize_dict(obj, annotation, context)

    # handle value collections
    if isinstance(obj, (list, tuple)):
        return _serialize_list_or_tuple(obj, annotation, context)
    elif isinstance(obj, (set, frozenset)):
        return _serialize_set(obj, annotation, context)
    else:
        # range, Generator
        return _serialize_list_or_tuple(list(obj), annotation, context)


def _serialize_list_or_tuple(
    obj: list | tuple,
    annotation: Annotation,
    context: SerializationContext,
) -> list[Any]:
    """
    Serialize list or tuple to a list.
    """
    if len(annotation.arg_annotations) >= 1:
        item_ann = annotation.arg_annotations[0]
    else:
        item_ann = Annotation(type(obj[0])) if obj else Annotation(Any)

    return [context.serialize(o, item_ann) for o in obj]


def _serialize_set(
    obj: set | frozenset,
    annotation: Annotation,
    context: SerializationContext,
) -> list[Any]:
    """
    Serialize set to a list (sets aren't JSON-serializable).
    """
    if len(annotation.arg_annotations) >= 1:
        item_ann = annotation.arg_annotations[0]
    else:
        # infer from first element if available
        item_ann = Annotation(type(next(iter(obj)))) if obj else Annotation(Any)

    return [context.serialize(o, item_ann) for o in obj]


def _serialize_dict(
    obj: Mapping,
    annotation: Annotation,
    context: SerializationContext,
) -> dict[Any, Any]:
    """
    Serialize dict.
    """
    if len(annotation.arg_annotations) >= 2:
        key_ann, value_ann = annotation.arg_annotations[0:2]
    else:
        # infer from first item if available
        if obj:
            first_key, first_val = next(iter(obj.items()))
            key_ann = Annotation(type(first_key))
            value_ann = Annotation(type(first_val))
        else:
            key_ann, value_ann = Annotation(Any), Annotation(Any)

    return {
        context.serialize(k, key_ann): context.serialize(v, value_ann)
        for k, v in obj.items()
    }

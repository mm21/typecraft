"""
Serialization capability.
"""

from __future__ import annotations

import inspect
from collections import defaultdict
from types import EllipsisType
from typing import (
    Any,
    Callable,
    Sequence,
    cast,
    overload,
)

from ._utils import ConverterSignature, normalize_to_registry
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
Function which serializes the given object from a specific source type and generally
returns an object of built-in Python types.

Can optionally take the annotation and context, generally used to propagate to nested
objects (e.g. elements of custom collections).
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
        source_annotation: Annotation | Any,
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
        self.__source_annotation = Annotation._normalize(source_annotation)
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

    @classmethod
    def from_func(
        cls,
        func: SerializerFuncType[T],
        *,
        variance: VarianceType = "contravariant",
    ) -> TypedSerializer[T]:
        """
        Create a TypedSerializer from a function by inspecting its signature.
        """
        sig = ConverterSignature.from_func(func, SerializationContext)
        return TypedSerializer(sig.obj_param.annotation, func=func, variance=variance)

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

    def can_serialize(self, obj: Any, source_annotation: Annotation | Any, /) -> bool:
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

    @overload
    def register(self, serializer: TypedSerializer, /): ...

    @overload
    def register(
        self, func: SerializerFuncType, /, *, variance: VarianceType = "contravariant"
    ): ...

    def register(
        self,
        serializer_or_func: TypedSerializer | SerializerFuncType,
        /,
        *,
        variance: VarianceType = "contravariant",
    ):
        """
        Register a serializer.
        """
        serializer = (
            serializer_or_func
            if isinstance(serializer_or_func, TypedSerializer)
            else TypedSerializer.from_func(serializer_or_func, variance=variance)
        )
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
        Register multiple serializers.
        """
        for serializer in serializers:
            self.register(serializer)


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

    def serialize(self, obj: Any, source_type: Annotation | Any, /) -> Any:
        """
        Serialize object using registered typed serializers.

        Walks the object recursively in lockstep with the source annotation,
        invoking type-based serializers when they match.
        """
        source_ann = Annotation._normalize(source_type)
        return _dispatch_serialization(obj, source_ann, self)


@overload
def serialize(
    obj: Any,
    source_type: Annotation | Any,
    /,
    *serializers: TypedSerializer,
) -> Any: ...


@overload
def serialize(
    obj: Any,
    source_type: Annotation | Any,
    registry: TypedSerializerRegistry,
    /,
) -> Any: ...


def serialize(
    obj: Any,
    source_type: Annotation | Any,
    /,
    *serializers_or_registry: TypedSerializer | TypedSerializerRegistry,
) -> Any:
    """
    Recursively serialize object by type, generally to built-in Python types.

    Handles nested parameterized types like list[MyClass] by recursively
    applying serialization at each level.
    """
    registry = normalize_to_registry(
        TypedSerializer, TypedSerializerRegistry, *serializers_or_registry
    )
    context = SerializationContext(registry=registry)
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
    if issubclass(annotation.concrete_type, COLLECTION_TYPES):
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

    assert len(
        annotation.arg_annotations
    ), f"Collection annotation has no type parameter: {annotation}"

    type_ = annotation.concrete_type

    # handle conversion from mappings
    if issubclass(type_, dict):
        assert isinstance(obj, type_)
        return _serialize_dict(obj, annotation, context)

    # handle conversion from value collections
    if issubclass(type_, list):
        assert isinstance(obj, type_)
        return _serialize_list(obj, annotation, context)
    elif issubclass(type_, tuple):
        assert isinstance(obj, type_)
        return _serialize_tuple(obj, annotation, context)
    else:
        assert issubclass(type_, (set, frozenset))
        assert isinstance(obj, type_)
        return _serialize_set(obj, annotation, context)


def _serialize_list(
    obj: list[Any],
    annotation: Annotation,
    context: SerializationContext,
) -> list[Any]:
    """
    Serialize list to a list.
    """
    assert len(annotation.arg_annotations) >= 1
    item_ann = annotation.arg_annotations[0]

    return [context.serialize(o, item_ann) for o in obj]


def _serialize_tuple(
    obj: tuple[Any],
    annotation: Annotation,
    context: SerializationContext,
) -> list[Any]:
    """
    Serialize tuple to a list.
    """
    assert len(annotation.arg_annotations) >= 1

    # check for Ellipsis (tuple[T, ...])
    if annotation.arg_annotations[-1].concrete_type is EllipsisType:
        # variable-length tuple: use first annotation for all items
        item_ann = annotation.arg_annotations[0]
        return [context.serialize(o, item_ann) for o in obj]
    else:
        # fixed-length tuple: match annotations to items
        assert len(annotation.arg_annotations) == len(obj), (
            f"Tuple length mismatch: expected {len(annotation.arg_annotations)} items, "
            f"got {len(obj)}"
        )
        return [
            context.serialize(o, ann) for o, ann in zip(obj, annotation.arg_annotations)
        ]


def _serialize_set(
    obj: set[Any] | frozenset[Any],
    annotation: Annotation,
    context: SerializationContext,
) -> list[Any]:
    """
    Serialize set to a list (sets aren't JSON-serializable).
    """
    assert len(annotation.arg_annotations) == 1
    item_ann = annotation.arg_annotations[0]

    return [context.serialize(o, item_ann) for o in obj]


def _serialize_dict(
    obj: dict[Any, Any],
    annotation: Annotation,
    context: SerializationContext,
) -> dict[Any, Any]:
    """
    Serialize dict.
    """
    assert len(annotation.arg_annotations) == 2
    key_ann, value_ann = annotation.arg_annotations

    return {
        context.serialize(k, key_ann): context.serialize(v, value_ann)
        for k, v in obj.items()
    }

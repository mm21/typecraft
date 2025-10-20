"""
Serialization capability.
"""

from __future__ import annotations

from types import EllipsisType
from typing import (
    Any,
    Callable,
    cast,
    overload,
)

from .converting import (
    BaseConversionContext,
    BaseConverterRegistry,
    BaseTypedConverter,
    ConverterFunction,
    normalize_to_registry,
)
from .inspecting.annotations import Annotation
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


type SerializerFuncType[SourceT] = Callable[[SourceT], Any] | Callable[
    [SourceT, Annotation, SerializationContext], Any
]
"""
Function which serializes the given object from a specific source type and generally
returns an object of built-in Python types.

Can optionally take the annotation and context, generally used to propagate to nested
objects (e.g. elements of custom collections).
"""


class TypedSerializer[SourceT](BaseTypedConverter[SerializerFuncType[SourceT]]):
    """
    Encapsulates serialization parameters from a source annotation.
    """

    @overload
    def __init__(
        self,
        source_annotation: type[SourceT],
        target_annotation: Annotation | Any = Any,
        /,
        *,
        func: SerializerFuncType[SourceT] | None = None,
        variance: VarianceType = "contravariant",
    ): ...

    @overload
    def __init__(
        self,
        source_annotation: Annotation | Any,
        target_annotation: Annotation | Any = Any,
        /,
        *,
        func: SerializerFuncType | None = None,
        variance: VarianceType = "contravariant",
    ): ...

    def __init__(
        self,
        source_annotation: Any,
        target_annotation: Annotation | Any = Any,
        /,
        *,
        func: SerializerFuncType | None = None,
        variance: VarianceType = "contravariant",
    ):
        super().__init__(
            source_annotation, target_annotation, func=func, variance=variance
        )

    def __repr__(self) -> str:
        return f"TypedSerializer(source={self._source_annotation}, func={self._func}, variance={self._variance})"

    @classmethod
    def from_func(
        cls,
        func: SerializerFuncType[SourceT],
        *,
        variance: VarianceType = "contravariant",
    ) -> TypedSerializer[SourceT]:
        """
        Create a TypedSerializer from a function by inspecting its signature.
        """
        sig = ConverterFunction(func, SerializationContext)

        # validate sig: must take source type
        assert sig.obj_param.annotation

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
        assert self.can_convert(obj, source_annotation)

        # invoke serialization function
        try:
            if func := self._func:
                # provided validation function
                serialized_obj = func.invoke(obj, source_annotation, context)
            else:
                # direct object construction
                concrete_type = cast(
                    Callable[[SourceT], Any], self._target_annotation.concrete_type
                )
                serialized_obj = concrete_type(obj)
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"TypedSerializer {self} failed to serialize {obj} ({type(obj)}): {e}"
            ) from None

        return serialized_obj

    def can_convert(self, obj: Any, annotation: Annotation, /) -> bool:
        """
        Check if this serializer can serialize the given object from the given
        source annotation.
        """
        source_ann = Annotation._normalize(annotation)

        if not self._check_variance_match(source_ann, self._source_annotation):
            return False

        return source_ann.is_type(obj)

    def _get_context_cls(self) -> type[Any]:
        return SerializationContext


class TypedSerializerRegistry(BaseConverterRegistry[TypedSerializer]):
    """
    Registry for managing type serializers.

    Provides efficient lookup of serializers based on source object type
    and source annotation.
    """

    def __repr__(self) -> str:
        return f"TypedSerializerRegistry(serializers={self._converters})"

    @property
    def serializers(self) -> list[TypedSerializer]:
        """
        Get serializers currently registered.
        """
        return self._converters

    def _get_map_key_type(self, converter: TypedSerializer) -> type:
        """
        Get the source type to use as key in the serializer map.
        """
        return converter.source_annotation.concrete_type

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
        self._register_converter(serializer)


class SerializationContext(BaseConversionContext[TypedSerializerRegistry]):
    """
    Encapsulates serialization parameters, propagated throughout the
    serialization process.
    """

    def __repr__(self) -> str:
        return f"SerializationContext(registry={self._registry})"

    def _create_default_registry(self) -> TypedSerializerRegistry:
        return TypedSerializerRegistry()

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

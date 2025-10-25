"""
Serialization capability.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    ConverterFunctionWrapper,
    ConverterFuncType,
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


type SerializerFuncType[SourceT] = ConverterFuncType[SourceT, Any, SerializationInfo]
"""
Function which serializes the given object from a specific source type and generally
returns an object of built-in Python type. Can optionally take
`SerializationInfo` as the second argument.
"""


@dataclass
class SerializationInfo:
    """
    Info passed to a serialization function.
    """

    source_annotation: Annotation
    context: SerializationContext


class TypedSerializer[SourceT](BaseTypedConverter[SourceT, Any, SerializationInfo]):
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
        sig = ConverterFunctionWrapper[SourceT, Any, SerializationContext](func)

        # validate sig: must take source type
        assert sig.obj_param.annotation

        return TypedSerializer(sig.obj_param.annotation, func=func, variance=variance)

    def serialize(self, obj: Any, info: SerializationInfo, /) -> Any:
        """
        Serialize object or raise `ValueError`.

        `source_annotation` is required because some serializers may inspect it
        to recurse into items of collections.
        """

        # invoke serialization function
        try:
            if func := self._func:
                # provided validation function
                serialized_obj = func.invoke(obj, info)
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
        info = SerializationInfo(source_ann, self)
        return _dispatch_serialization(obj, info)


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
    info: SerializationInfo,
) -> Any:
    """
    Main serialization dispatcher.
    """

    # handle None
    if obj is None:
        return None

    # handle union type
    if info.source_annotation.is_union:
        return _serialize_union(obj, info)

    # try user-provided serializers first (even for primitives/collections)
    if serializer := info.context.registry.find(obj, info.source_annotation):
        return serializer.serialize(obj, info)

    # handle builtin collections
    if issubclass(info.source_annotation.concrete_type, COLLECTION_TYPES):
        return _serialize_collection(obj, info)

    # no serializer found, return as-is
    return obj


def _serialize_union(obj: Any, info: SerializationInfo) -> Any:
    """
    Serialize union types by finding the matching constituent type.
    """
    for arg in info.source_annotation.arg_annotations:
        if arg.is_type(obj):
            return _dispatch_serialization(obj, SerializationInfo(arg, info.context))

    # no matching union member, serialize with inferred type
    return _dispatch_serialization(
        obj, SerializationInfo(Annotation(type(obj)), info.context)
    )


def _serialize_collection(
    obj: CollectionType,
    info: SerializationInfo,
) -> Any:
    """
    Serialize collection of objects.
    """

    assert len(
        info.source_annotation.arg_annotations
    ), f"Collection annotation has no type parameter: {info.source_annotation}"

    type_ = info.source_annotation.concrete_type

    # handle conversion from mappings
    if issubclass(type_, dict):
        assert isinstance(obj, type_)
        return _serialize_dict(obj, info)

    # handle conversion from value collections
    if issubclass(type_, list):
        assert isinstance(obj, type_)
        return _serialize_list(obj, info)
    elif issubclass(type_, tuple):
        assert isinstance(obj, type_)
        return _serialize_tuple(obj, info)
    else:
        assert issubclass(type_, (set, frozenset))
        assert isinstance(obj, type_)
        return _serialize_set(obj, info)


def _serialize_list(
    obj: list[Any],
    info: SerializationInfo,
) -> list[Any]:
    """
    Serialize list to a list.
    """
    ann, context = info.source_annotation, info.context

    assert len(ann.arg_annotations) >= 1
    item_ann = ann.arg_annotations[0]

    return [context.serialize(o, item_ann) for o in obj]


def _serialize_tuple(
    obj: tuple[Any],
    info: SerializationInfo,
) -> list[Any]:
    """
    Serialize tuple to a list.
    """
    ann, context = info.source_annotation, info.context

    assert len(ann.arg_annotations) >= 1

    # check for Ellipsis (tuple[T, ...])
    if ann.arg_annotations[-1].concrete_type is EllipsisType:
        # variable-length tuple: use first annotation for all items
        item_ann = ann.arg_annotations[0]
        return [context.serialize(o, item_ann) for o in obj]
    else:
        # fixed-length tuple: match annotations to items
        assert len(ann.arg_annotations) == len(obj), (
            f"Tuple length mismatch: expected {len(ann.arg_annotations)} items, "
            f"got {len(obj)}"
        )
        return [context.serialize(o, ann) for o, ann in zip(obj, ann.arg_annotations)]


def _serialize_set(
    obj: set[Any] | frozenset[Any],
    info: SerializationInfo,
) -> list[Any]:
    """
    Serialize set to a list (sets aren't JSON-serializable).
    """
    ann, context = info.source_annotation, info.context

    assert len(ann.arg_annotations) == 1
    item_ann = ann.arg_annotations[0]

    return [context.serialize(o, item_ann) for o in obj]


def _serialize_dict(
    obj: dict[Any, Any],
    info: SerializationInfo,
) -> dict[Any, Any]:
    """
    Serialize dict.
    """
    ann, context = info.source_annotation, info.context

    assert len(ann.arg_annotations) == 2
    key_ann, value_ann = ann.arg_annotations

    return {
        context.serialize(k, key_ann): context.serialize(v, value_ann)
        for k, v in obj.items()
    }

"""
Serialization capability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import EllipsisType
from typing import (
    Any,
    Callable,
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
    CollectionType,
    VarianceType,
)

__all__ = [
    "SerializerFuncType",
    "SerializationEngine",
    "TypedSerializer",
    "SerializerRegistry",
    "serialize",
]


type SerializerFuncType[SourceT] = ConverterFuncType[SourceT, Any, SerializationHandle]
"""
Function which serializes the given object from a specific source type and generally
returns an object of built-in Python type. Can optionally take
`SerializationHandle` as the second argument.
"""


@dataclass(kw_only=True)
class SerializationParams:
    """
    Serialization params as passed by user.
    """

    pass  # placeholder for future parameters


@dataclass(kw_only=True)
class SerializationFrame:
    """
    Internal recursion state. A new object is created for each recursion level.
    """

    source_annotation: Annotation
    """
    Source type we're serializing from.
    """

    params: SerializationParams
    """
    Parameters passed at serialization entry point.
    """

    context: Any
    """
    User context passed at serialization entry point.
    """

    engine: SerializationEngine
    """
    Reference to serialization engine for manual recursion.
    """

    path: tuple[str | int, ...] = field(default_factory=tuple)
    """
    Field path at this level in recursion.
    """

    def recurse(
        self,
        obj: Any,
        source_annotation: Annotation,
        path_name: str | int,
        context: Any | None = None,
    ) -> Any:
        next_frame = SerializationFrame(
            source_annotation=source_annotation,
            params=self.params,
            context=context if context is not None else self.context,
            engine=self.engine,
            path=tuple(list(self.path) + [path_name]),
        )
        return self.engine.serialize(obj, next_frame)

    @classmethod
    def _new(
        cls,
        source_annotation: Annotation,
        params: SerializationParams,
        context: Any,
        engine: SerializationEngine,
    ) -> SerializationFrame:
        return SerializationFrame(
            source_annotation=source_annotation,
            params=params,
            context=context,
            path=(),
            engine=engine,
        )

    def _with_annotation(self, annotation: Annotation) -> SerializationFrame:
        """
        Create a new frame with the annotation replaced.
        """
        return SerializationFrame(
            source_annotation=annotation,
            params=self.params,
            context=self.context,
            engine=self.engine,
            path=self.path,
        )


class SerializationHandle:
    """
    User-facing interface to state and operations, passed to custom `serialize()`
    functions.
    """

    _frame: SerializationFrame

    def __init__(self, frame: SerializationFrame):
        self._frame = frame

    @property
    def source_annotation(self) -> Annotation:
        return self._frame.source_annotation

    @property
    def params(self) -> SerializationParams:
        return self._frame.params

    @property
    def context(self) -> Any:
        return self._frame.context

    def recurse(
        self,
        obj: Any,
        source_annotation: Annotation,
        path_name: str | int,
        /,
        *,
        context: Any | None = None,
    ) -> Any:
        """
        Recurse into serialization, overriding context if passed.
        """
        return self._frame.recurse(obj, source_annotation, path_name, context)


class TypedSerializer[SourceT](BaseTypedConverter[SourceT, Any, SerializationHandle]):
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

    def serialize(self, obj: Any, handle: SerializationHandle, /) -> Any:
        """
        Serialize object or raise `ValueError`.

        `source_annotation` is required because some serializers may inspect it
        to recurse into items of collections.
        """

        # invoke serialization function
        try:
            if func := self._func:
                # provided validation function
                serialized_obj = func.invoke(obj, handle)
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

        if not self._target_annotation.is_type(serialized_obj):
            raise ValueError(
                f"TypedSerializer {self} failed to serialize {obj} ({type(obj)}), got {serialized_obj} ({type(serialized_obj)})"
            )

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


class SerializerRegistry(BaseConverterRegistry[TypedSerializer]):
    """
    Registry for managing type serializers.

    Provides efficient lookup of serializers based on source object type
    and source annotation.
    """

    def __repr__(self) -> str:
        return f"SerializerRegistry(serializers={self._converters})"

    @property
    def serializers(self) -> list[TypedSerializer]:
        """
        Get serializers currently registered.
        """
        return self._converters

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


class SerializationEngine(BaseConversionEngine[SerializerRegistry]):
    """
    Orchestrates serialization process. Not exposed to user.
    """

    def serialize(self, obj: Any, frame: SerializationFrame, /) -> Any:
        """
        Serialize object using registered typed serializers.

        Walks the object recursively in lockstep with the source annotation,
        invoking type-based serializers when they match.
        """
        return _dispatch_serialization(obj, frame)


@overload
def serialize(
    obj: Any,
    source_type: Annotation | Any,
    /,
    *serializers: TypedSerializer,
    context: Any = None,
) -> Any: ...


@overload
def serialize(
    obj: Any,
    source_type: Annotation | Any,
    registry: SerializerRegistry,
    /,
    *,
    context: Any = None,
) -> Any: ...


def serialize(
    obj: Any,
    source_type: Annotation | Any,
    /,
    *serializers_or_registry: TypedSerializer | SerializerRegistry,
    context: Any = None,
) -> Any:
    """
    Recursively serialize object by type, generally to built-in Python types.

    Handles nested parameterized types like list[MyClass] by recursively
    applying serialization at each level.
    """
    source_annotation = Annotation._normalize(source_type)
    registry = normalize_to_registry(
        TypedSerializer, SerializerRegistry, *serializers_or_registry
    )
    engine = SerializationEngine(registry=registry)
    params = SerializationParams()
    frame = SerializationFrame._new(source_annotation, params, context, engine)
    return engine.serialize(obj, frame)


def _dispatch_serialization(
    obj: Any,
    frame: SerializationFrame,
) -> Any:
    """
    Main serialization dispatcher.
    """

    # handle None
    if obj is None:
        return None

    # handle union type
    if frame.source_annotation.is_union:
        return _serialize_union(obj, frame)

    # try user-provided serializers first (even for primitives/collections)
    if serializer := frame.engine.registry.find(obj, frame.source_annotation):
        return serializer.serialize(obj, SerializationHandle(frame))

    # handle builtin collections
    if issubclass(frame.source_annotation.concrete_type, COLLECTION_TYPES):
        return _serialize_collection(obj, frame)

    # no serializer found, return as-is
    return obj


def _serialize_union(obj: Any, frame: SerializationFrame) -> Any:
    """
    Serialize union types by finding the matching constituent type.
    """
    for arg in frame.source_annotation.arg_annotations:
        if arg.is_type(obj):
            return frame.engine.serialize(obj, frame._with_annotation(arg))

    # no matching union member, serialize with inferred type
    return frame.engine.serialize(obj, frame._with_annotation(Annotation(type(obj))))


def _serialize_collection(
    obj: CollectionType,
    frame: SerializationFrame,
) -> Any:
    """
    Serialize collection of objects.
    """

    assert len(
        frame.source_annotation.arg_annotations
    ), f"Collection annotation has no type parameter: {frame.source_annotation}"

    type_ = frame.source_annotation.concrete_type

    # handle conversion from mappings
    if issubclass(type_, dict):
        assert isinstance(obj, type_)
        return _serialize_dict(obj, frame)

    # handle conversion from value collections
    if issubclass(type_, list):
        assert isinstance(obj, type_)
        return _serialize_list(obj, frame)
    elif issubclass(type_, tuple):
        assert isinstance(obj, type_)
        return _serialize_tuple(obj, frame)
    else:
        assert issubclass(type_, (set, frozenset))
        assert isinstance(obj, type_)
        return _serialize_set(obj, frame)


def _serialize_list(
    obj: list[Any],
    frame: SerializationFrame,
) -> list[Any]:
    """
    Serialize list to a list.
    """
    assert len(frame.source_annotation.arg_annotations) >= 1
    item_ann = frame.source_annotation.arg_annotations[0]

    return [frame.recurse(o, item_ann, i) for i, o in enumerate(obj)]


def _serialize_tuple(
    obj: tuple[Any],
    frame: SerializationFrame,
) -> list[Any]:
    """
    Serialize tuple to a list.
    """
    assert len(frame.source_annotation.arg_annotations) >= 1

    # check for Ellipsis (tuple[T, ...])
    if frame.source_annotation.arg_annotations[-1].concrete_type is EllipsisType:
        # variable-length tuple: use first annotation for all items
        item_ann = frame.source_annotation.arg_annotations[0]
        return [frame.recurse(o, item_ann, i) for i, o in enumerate(obj)]
    else:
        # fixed-length tuple: match annotations to items
        assert len(frame.source_annotation.arg_annotations) == len(obj), (
            f"Tuple length mismatch: expected {len(frame.source_annotation.arg_annotations)} items, "
            f"got {len(obj)}"
        )
        return [
            frame.recurse(o, ann, i)
            for i, (o, ann) in enumerate(
                zip(obj, frame.source_annotation.arg_annotations)
            )
        ]


def _serialize_set(
    obj: set[Any] | frozenset[Any],
    frame: SerializationFrame,
) -> list[Any]:
    """
    Serialize set to a list (sets aren't JSON-serializable).
    """
    assert len(frame.source_annotation.arg_annotations) == 1
    item_ann = frame.source_annotation.arg_annotations[0]

    return [frame.recurse(o, item_ann, i) for i, o in enumerate(obj)]


def _serialize_dict(
    obj: dict[Any, Any],
    frame: SerializationFrame,
) -> dict[Any, Any]:
    """
    Serialize dict.
    """
    assert len(frame.source_annotation.arg_annotations) == 2
    key_ann, value_ann = frame.source_annotation.arg_annotations

    return {
        frame.recurse(k, key_ann, f"key[{i}]"): frame.recurse(
            v, value_ann, f"value[{i}]"
        )
        for i, (k, v) in enumerate(obj.items())
    }

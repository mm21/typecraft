"""
Serialization capability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Literal,
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
from .inspecting.annotations import ANY, Annotation
from .typedefs import (
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

    mode: Literal["json", "plain"] = "json"
    """
    Serialization mode:
    - "plain": serialize without special handling
    - "json": apply converters to ensure JSON-serializable output
    """


@dataclass(kw_only=True)
class SerializationFrame:
    """
    Internal recursion state. A new object is created for each recursion level.
    """

    source_annotation: Annotation | None
    """
    Optional source type annotation for type-specific serialization.
    If None, type is inferred from the object.
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
        path_name: str | int,
        source_annotation: Annotation | None = None,
        context: Any | None = None,
    ) -> Any:
        next_frame = SerializationFrame(
            source_annotation=source_annotation,
            params=self.params,
            context=context if context is not None else self.context,
            engine=self.engine,
            path=tuple(list(self.path) + [path_name]),
        )
        return self.engine.process(obj, next_frame)

    @classmethod
    def _new(
        cls,
        source_annotation: Annotation | None,
        params: SerializationParams,
        context: Any,
        engine: SerializationEngine,
    ) -> SerializationFrame:
        return SerializationFrame(
            source_annotation=source_annotation,
            params=params,
            context=context,
            engine=engine,
            path=(),
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
    def source_annotation(self) -> Annotation | None:
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
        path_name: str | int,
        /,
        *,
        source_annotation: Annotation | None = None,
        context: Any | None = None,
    ) -> Any:
        """
        Recurse into serialization, optionally overriding source annotation and context.
        """
        return self._frame.recurse(obj, path_name, source_annotation, context)


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
                # provided function
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


class SerializationEngine(BaseConversionEngine[SerializerRegistry, SerializationFrame]):
    """
    Orchestrates serialization process. Not exposed to user.
    """

    def _get_builtin_registries(
        self, frame: SerializationFrame
    ) -> tuple[SerializerRegistry, ...]:
        return (JSON_REGISTRY,) if frame.params.mode == "json" else ()

    def _should_convert(self, obj: Any, frame: SerializationFrame) -> bool:
        """
        Check if serialization conversion is needed.
        """
        # TODO: if mode == "json", check if json-serializable
        # - generic mechanism based on possible source annotations of all registries
        _ = obj, frame
        return True

    def _handle_missing_converter(self, obj: Any, frame: SerializationFrame):
        # TODO: if mode == "json", raise error
        _ = frame
        return obj

    def _get_ref_annotation(self, obj: Any, frame: SerializationFrame) -> Annotation:
        """
        Get annotation for finding converters.

        Uses provided source_annotation if available, otherwise infers from object type.
        """
        if frame.source_annotation is not None and frame.source_annotation != ANY:
            return frame.source_annotation
        return Annotation(type(obj))

    def _apply_converter(
        self, converter: TypedSerializer, obj: Any, frame: SerializationFrame
    ) -> Any:
        """
        Apply serializer to convert the object.
        """
        return converter.serialize(obj, SerializationHandle(frame))

    def _convert_union(self, obj: Any, frame: SerializationFrame) -> Any:
        """
        Serialize union types by finding the matching constituent type.
        """
        ref_annotation = self._get_ref_annotation(obj, frame)

        for ann in ref_annotation.arg_annotations:
            if ann.is_type(obj):
                # recurse with the matching union member type
                return self.process(obj, frame._with_annotation(ann))

        # no matching union member, serialize with inferred type
        return self.process(obj, frame)

    def _convert_list(self, obj: list[Any], frame: SerializationFrame) -> list[Any]:
        """
        Serialize list to a list by recursing into items.
        """
        ref_annotation = self._get_ref_annotation(obj, frame)

        # extract item annotation if available
        if len(ref_annotation.arg_annotations):
            assert len(ref_annotation.arg_annotations) == 1
            item_ann = ref_annotation.arg_annotations[0]
        else:
            item_ann = ANY

        return [
            frame.recurse(o, i, source_annotation=item_ann) for i, o in enumerate(obj)
        ]

    def _convert_tuple(self, obj: tuple[Any], frame: SerializationFrame) -> list[Any]:
        """
        Serialize tuple to a list by recursing into items.
        """
        ref_annotation = self._get_ref_annotation(obj, frame)

        # check if we have type annotations
        if ref_annotation.arg_annotations:
            # check for variable-length tuple (tuple[T, ...])
            if (
                len(ref_annotation.arg_annotations) == 2
                and ref_annotation.arg_annotations[-1].raw is ...
            ):
                # variable-length: use first annotation for all items
                item_ann = ref_annotation.arg_annotations[0]
                return [
                    frame.recurse(o, i, source_annotation=item_ann)
                    for i, o in enumerate(obj)
                ]
            elif len(ref_annotation.arg_annotations) == len(obj):
                # fixed-length: match annotations to items
                return [
                    frame.recurse(o, i, source_annotation=ann)
                    for i, (o, ann) in enumerate(
                        zip(obj, ref_annotation.arg_annotations)
                    )
                ]
            else:
                raise ValueError(
                    f"Object {obj} does not have expected number of elements: expected {len(ref_annotation.arg_annotations)}, got {len(obj)}"
                )

        # no annotations, infer from objects
        return [frame.recurse(o, i) for i, o in enumerate(obj)]

    def _convert_set(
        self, obj: set[Any] | frozenset[Any], frame: SerializationFrame
    ) -> list[Any]:
        """
        Serialize set to a list by recursing into items.
        """
        ref_annotation = self._get_ref_annotation(obj, frame)

        # extract item annotation if available
        if len(ref_annotation.arg_annotations):
            assert len(ref_annotation.arg_annotations) == 1
            item_ann = ref_annotation.arg_annotations[0]
        else:
            item_ann = ANY

        return [
            frame.recurse(o, i, source_annotation=item_ann) for i, o in enumerate(obj)
        ]

    def _convert_dict(
        self, obj: dict[Any, Any], frame: SerializationFrame
    ) -> dict[Any, Any]:
        """
        Serialize dict by recursing into keys and values.
        """
        ref_annotation = self._get_ref_annotation(obj, frame)

        # extract key and value annotations if available
        if len(ref_annotation.arg_annotations):
            assert len(ref_annotation.arg_annotations) == 2
            key_ann = ref_annotation.arg_annotations[0]
            value_ann = ref_annotation.arg_annotations[1]
        else:
            key_ann = ANY
            value_ann = ANY

        return {
            frame.recurse(k, f"key[{i}]", source_annotation=key_ann): frame.recurse(
                v, f"value[{i}]", source_annotation=value_ann
            )
            for i, (k, v) in enumerate(obj.items())
        }


@overload
def serialize(
    obj: Any,
    /,
    *serializers: TypedSerializer,
    source_type: Annotation | Any | None = None,
    mode: Literal["json", "plain"] = "json",
    context: Any = None,
) -> Any: ...


@overload
def serialize(
    obj: Any,
    registry: SerializerRegistry,
    /,
    *,
    source_type: Annotation | Any | None = None,
    mode: Literal["json", "plain"] = "json",
    context: Any = None,
) -> Any: ...


def serialize(
    obj: Any,
    /,
    *serializers_or_registry: TypedSerializer | SerializerRegistry,
    source_type: Annotation | Any | None = None,
    mode: Literal["json", "plain"] = "json",
    context: Any = None,
) -> Any:
    """
    Recursively serialize object by type, generally to built-in Python types.

    Handles nested parameterized types by recursively applying serialization
    at each level based on the actual object types (or optionally specified source type).

    Args:
        obj: Object to serialize
        source_type: Optional source type annotation for type-specific serialization.
                    If None, type is inferred from the object.
        mode: "plain" for basic serialization, "json" to ensure JSON-compatible output
        context: User-defined context passed to serializers
    """
    source_annotation = (
        Annotation._normalize(source_type) if source_type is not None else None
    )
    registry = normalize_to_registry(
        TypedSerializer, SerializerRegistry, *serializers_or_registry
    )
    engine = SerializationEngine(registry=registry)
    params = SerializationParams(mode=mode)
    frame = SerializationFrame._new(source_annotation, params, context, engine)
    return engine.process(obj, frame)


# TODO
JSON_REGISTRY = SerializerRegistry()
"""
Registry to use for json-mode serialization.
"""

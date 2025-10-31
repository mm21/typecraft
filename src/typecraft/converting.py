"""
Low-level conversion capability, agnostic of validation vs serialization.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any, Self, cast

from .inspecting.annotations import ANY, Annotation
from .inspecting.classes import extract_type_param
from .inspecting.functions import ParameterInfo, SignatureInfo
from .typedefs import COLLECTION_TYPES, VarianceType

type ConverterFuncType[SourceT, TargetT, HandleT] = Callable[
    [SourceT], TargetT
] | Callable[[SourceT, HandleT], TargetT]
"""
Function which converts an object. Can take the source object by itself or
source object with info.
"""


class ConverterFunctionWrapper[SourceT, TargetT, HandleT]:
    """
    Encapsulates a validator or serializer function.
    """

    func: ConverterFuncType[SourceT, TargetT, HandleT]
    """
    Converter function.
    """

    sig_info: SignatureInfo
    """
    Function signature.
    """

    obj_param: ParameterInfo
    """
    Parameter for object to be validated/serialized, must be positional.
    """

    handle_param: ParameterInfo | None
    """
    Parameter for additional info, must be positional.
    """

    def __init__(self, func: Callable[..., Any]):
        sig_info = SignatureInfo(func)

        # get object parameter
        obj_param = next(
            (p for p in sig_info.get_params(positional=True)),
            None,
        )
        assert (
            obj_param
        ), f"Function {func} does not take any positional params, must take obj as positional"

        # get handle parameter
        handle_param = sig_info.get_param("handle")
        if handle_param:
            assert (
                handle_param.index == 1
            ), f"Function {func} must take handle as second positional argument, got index {handle_param.index}"

        self.func = func
        self.sig_info = sig_info
        self.obj_param = obj_param
        self.handle_param = handle_param

    def invoke(self, obj: SourceT, handle: HandleT, /) -> TargetT:
        if self.handle_param:
            # invoke with info
            func = cast(Callable[[SourceT, HandleT], TargetT], self.func)
            return func(obj, handle)
        else:
            # invoke without info
            func = cast(Callable[[SourceT], TargetT], self.func)
            return func(obj)


@dataclass(kw_only=True)
class BaseConversionFrame[ParamsT]:

    source_annotation: Annotation
    """
    Source type we're converting from.
    """

    target_annotation: Annotation
    """
    Target type we're converting to.
    """

    context: Any
    """
    User context passed at validation entry point.
    """

    params: ParamsT
    """
    Parameters passed at validation entry point.
    """

    engine: BaseConversionEngine
    """
    Conversion engine for recursion.
    """

    path: tuple[str | int, ...] = field(default_factory=tuple)
    """
    Field path at this level in recursion.
    """

    seen: set[int] = field(default_factory=set)
    """
    Object ids for cycle detection.
    """

    def recurse(
        self,
        obj: Any,
        path_segment: str | int,
        /,
        *,
        source_annotation: Annotation = ANY,
        target_annotation: Annotation = ANY,
        context: Any | None = None,
    ) -> Any:
        """
        Create a new frame and recurse using the engine.
        """
        next_frame = self.copy(
            source_annotation=source_annotation,
            target_annotation=target_annotation,
            context=context,
            path_append=path_segment,
        )

        # recurse and add/remove this object before/after
        next_frame.seen.add(id(obj))
        next_obj = self.engine.process(obj, next_frame)
        next_frame.seen.remove(id(obj))

        return next_obj

    def copy(
        self,
        *,
        source_annotation: Annotation | None = None,
        target_annotation: Annotation | None = None,
        context: Any | None = None,
        path_append: str | int | None = None,
    ) -> Self:
        """
        Create a new frame with the arguments replaced if not None.
        """
        path = (
            self.path if path_append is None else tuple(list(self.path) + [path_append])
        )
        return type(self)(
            source_annotation=source_annotation or self.source_annotation,
            target_annotation=target_annotation or self.target_annotation,
            context=context or self.context,
            params=self.params,
            engine=self.engine,
            path=path,
            seen=self.seen,
        )


class BaseConversionHandle[FrameT: BaseConversionFrame, ParamsT: Any]:
    """
    User-facing interface to state and operations, passed to custom `validate()`
    functions.
    """

    # TODO: __frame, once collection validators don't recurse
    _frame: FrameT

    def __init__(self, frame: FrameT, /):
        self._frame = frame

    @property
    def source_annotation(self) -> Annotation:
        return self._frame.source_annotation

    @property
    def target_annotation(self) -> Annotation:
        return self._frame.target_annotation

    @property
    def context(self) -> Any:
        return self._frame.context

    @property
    def params(self) -> ParamsT:
        return self._frame.params


class BaseConverter[SourceT, TargetT, HandleT](ABC):
    """
    Base class for typed converters (validators and serializers).

    Encapsulates common conversion parameters and logic for type-based
    conversion between source and target annotations.
    """

    _source_annotation: Annotation
    """
    Annotation specifying type to convert from.
    """

    _target_annotation: Annotation
    """
    Annotation specifying type to convert to.
    """

    _func_wrapper: ConverterFunctionWrapper[SourceT, TargetT, HandleT] | None
    """
    Function taking source type and returning an instance of target type.
    """

    _variance: VarianceType
    """
    Variance with respect to a reference annotation, either source or target depending
    on serialization vs validation.
    """

    def __init__(
        self,
        source_annotation: Any,
        target_annotation: Any,
        /,
        *,
        func: ConverterFuncType[SourceT, TargetT, HandleT] | None = None,
        variance: VarianceType = "contravariant",
    ):
        self._source_annotation = Annotation._normalize(source_annotation)
        self._target_annotation = Annotation._normalize(target_annotation)
        self._func_wrapper = ConverterFunctionWrapper(func) if func else None
        self._variance = variance

    @property
    def source_annotation(self) -> Annotation:
        return self._source_annotation

    @property
    def target_annotation(self) -> Annotation:
        return self._target_annotation

    @property
    def variance(self) -> VarianceType:
        return self._variance

    # TODO: source/target annotation
    @abstractmethod
    def can_convert(self, obj: Any, annotation: Annotation, /) -> bool:
        """
        Check if this converter can convert the given object with the given annotation.

        The meaning of 'annotation' depends on the converter type:
        - For validators: target annotation (converting TO)
        - For serializers: source annotation (converting FROM)
        """

    @classmethod
    def from_func(
        cls,
        func: ConverterFuncType[SourceT, TargetT, HandleT],
        /,
        *,
        variance: VarianceType = "contravariant",
    ) -> Self:
        """
        Create a TypedValidator from a function by inspecting its signature.
        """
        func_wrapper = ConverterFunctionWrapper[Any, TargetT, HandleT](func)

        # validate sig: input and return types must be annotated
        assert func_wrapper.obj_param.annotation
        assert func_wrapper.sig_info.return_annotation

        return cls(
            func_wrapper.obj_param.annotation,
            func_wrapper.sig_info.return_annotation,
            func=func,
            variance=variance,
        )

    def _check_variance_match(
        self,
        annotation: Annotation,
        ref_annotation: Annotation,
    ) -> bool:
        """Check if annotation matches reference based on variance."""
        if self._variance == "invariant":
            # exact match only
            return annotation == ref_annotation
        else:
            # contravariant (default): annotation must be a subclass of reference
            return annotation.is_subtype(ref_annotation)


# TODO: take BaseConverter, can be user-defined subclass (not based on type)
class BaseConverterRegistry[ConverterT: BaseConverter](ABC):
    """
    Base class for converter registries.

    Provides efficient lookup of converters based on object type and annotation.
    Converters are indexed by a key type for fast lookup, with fallback to
    sequential search for contravariant matching.
    """

    _converters: list[ConverterT]
    """
    List of all converters for fallback/contravariant matching.
    """

    def __init__(self, *converters: ConverterT):
        self._converters = []
        self.extend(converters)

    def __len__(self) -> int:
        return len(self._converters)

    def find(self, obj: Any, annotation: Annotation) -> ConverterT | None:
        """
        Find the first converter that can handle the conversion.
        """
        for converter in self._converters:
            if converter.can_convert(obj, annotation):
                return converter
        return None

    def extend(self, converters: Sequence[ConverterT]):
        """
        Register multiple converters.
        """
        for converter in converters:
            self._register_converter(converter)

    def _register_converter(self, converter: ConverterT):
        """
        Register a converter object.
        """
        self._converters.append(converter)

    @cached_property
    def _converter_cls(self) -> type[ConverterT]:
        converter_cls = extract_type_param(
            type(self), BaseConverterRegistry, "ConverterT", BaseConverter
        )
        return cast(type[ConverterT], converter_cls)


class BaseConversionEngine[RegistryT: BaseConverterRegistry, FrameT: Any](ABC):
    """
    Base class for conversion engines.

    Encapsulates conversion parameters and provides access to the converter
    registry, propagated throughout the conversion process. Contains common
    recursion logic with abstract hooks for validation/serialization-specific behavior.
    """

    __user_registry: RegistryT

    def __init__(self, *, registry: RegistryT | None = None):
        self.__user_registry = registry or self.__registry_cls()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(registry={self.__user_registry})"

    @property
    def registry(self) -> RegistryT:
        return self.__user_registry

    @property
    def __registry_cls(self) -> type[RegistryT]:
        registry_cls = extract_type_param(
            type(self), BaseConversionEngine, "RegistryT", BaseConverterRegistry
        )
        assert registry_cls
        return cast(type[RegistryT], registry_cls)

    def process(self, obj: Any, frame: FrameT) -> Any:
        """
        Main conversion dispatcher with common logic.

        Walks the object recursively based on reference annotation,
        invoking type-based converters when conversion is needed.
        """
        ref_annotation = self._get_ref_annotation(obj, frame)

        # handle union type
        if ref_annotation.is_union:
            return self._convert_union(obj, frame)

        # check if conversion is needed and apply converter
        if self._should_convert(obj, frame):
            if converter := self._find_converter(obj, frame, ref_annotation):
                return self._apply_converter(converter, obj, frame)
            obj = self._handle_missing_converter(obj, frame)

        # handle builtin collections by recursing into items
        if issubclass(ref_annotation.concrete_type, COLLECTION_TYPES):
            return self._convert_collection(obj, frame)

        # no conversion needed, return as-is
        return obj

    @abstractmethod
    def _get_builtin_registries(self, frame: FrameT) -> tuple[RegistryT, ...]:
        """
        Get builtin registries to use for conversion based on the parameters.
        """

    @abstractmethod
    def _should_convert(self, obj: Any, frame: FrameT) -> bool:
        """
        Check if conversion should be applied.

        - For validation: returns True if object type doesn't match target
        - For serialization: returns True if object needs conversion based on mode
        (e.g. json)
        """

    @abstractmethod
    def _handle_missing_converter(self, obj: Any, frame: FrameT) -> Any:
        """
        Handle situation where `_should_convert()` returned True, but no converter
        was found.
        """

    @abstractmethod
    def _get_ref_annotation(self, obj: Any, frame: FrameT) -> Annotation:
        """
        Get the annotation to use for finding converters and recursion.

        For validation: returns the target annotation
        For serialization: returns annotation inferred from object type
        """

    # TODO: generic BaseConversionEngine.convert()
    @abstractmethod
    def _apply_converter(self, converter: Any, obj: Any, frame: FrameT) -> Any:
        """
        Apply a converter to transform the object.
        """
        # TODO:
        # return converter.convert(obj, SerializationHandle(frame))

    @abstractmethod
    def _convert_union(self, obj: Any, frame: FrameT) -> Any:
        """
        Handle union type conversion.
        """

    # TODO: implement following collection processing in base
    @abstractmethod
    def _convert_list(self, obj: Any, frame: FrameT) -> Any:
        """Convert list by recursing into items."""

    @abstractmethod
    def _convert_tuple(self, obj: Any, frame: FrameT) -> Any:
        """Convert tuple by recursing into items."""

    @abstractmethod
    def _convert_set(self, obj: Any, frame: FrameT) -> Any:
        """Convert set by recursing into items."""

    @abstractmethod
    def _convert_dict(self, obj: Any, frame: FrameT) -> Any:
        """Convert dict by recursing into keys and values."""

    def _convert_collection(self, obj: Any, frame: FrameT) -> Any:
        """
        Convert collection by recursing into items.
        """
        ref_annotation = self._get_ref_annotation(obj, frame)
        type_ = ref_annotation.concrete_type

        # convert from mappings
        if issubclass(type_, dict):
            return self._convert_dict(obj, frame)

        # convert from value collections
        if issubclass(type_, list):
            return self._convert_list(obj, frame)
        elif issubclass(type_, tuple):
            return self._convert_tuple(obj, frame)
        else:
            assert issubclass(type_, (set, frozenset))
            return self._convert_set(obj, frame)

    # TODO: return BaseConverter
    def _find_converter(
        self, obj: Any, frame: FrameT, ref_annotation: Annotation
    ) -> BaseConverter | None:
        for registry in (self.__user_registry, *self._get_builtin_registries(frame)):
            if converter := registry.find(obj, ref_annotation):
                return converter
        return None


def normalize_to_registry[ConverterT, RegistryT](
    converter_cls: type[ConverterT],
    registry_cls: type[RegistryT],
    *converters_or_registry: Any,
) -> RegistryT:
    """
    Take converters or registry and return a registry.
    """
    if len(converters_or_registry) == 1 and isinstance(
        converters_or_registry[0], registry_cls
    ):
        registry = cast(RegistryT, converters_or_registry[0])
    else:
        assert all(isinstance(v, converter_cls) for v in converters_or_registry)
        converters = cast(tuple[ConverterT, ...], converters_or_registry)
        registry = registry_cls(*converters)
    return registry

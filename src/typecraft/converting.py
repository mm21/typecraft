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
from .typedefs import COLLECTION_TYPES

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


class ConverterInterface:
    """
    Defines the interface for converters and mixins.
    """

    def __init__(
        self,
        source_annotation: Any,
        target_annotation: Any,
        /,
        *,
        match_source_subtype: bool,
        match_target_subtype: bool,
    ):
        _ = (
            source_annotation,
            target_annotation,
            match_source_subtype,
            match_target_subtype,
        )


class BaseConverter[SourceT, TargetT, HandleT](ConverterInterface, ABC):
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

    _match_source_subtype: bool
    """
    Whether to match subtypes of the source annotation.
    """

    _match_target_subtype: bool
    """
    Whether to match subtypes of the target annotation.
    """

    def __init__(
        self,
        source_annotation: Any,
        target_annotation: Any,
        /,
        *,
        match_source_subtype: bool,
        match_target_subtype: bool,
    ):
        self._source_annotation = Annotation._normalize(source_annotation)
        self._target_annotation = Annotation._normalize(target_annotation)
        self._match_source_subtype = match_source_subtype
        self._match_target_subtype = match_target_subtype

    @property
    def source_annotation(self) -> Annotation:
        return self._source_annotation

    @property
    def target_annotation(self) -> Annotation:
        return self._target_annotation

    @property
    def match_source_subtype(self) -> bool:
        return self._match_source_subtype

    @property
    def match_target_subtype(self) -> bool:
        return self._match_target_subtype

    def check_match(
        self,
        source_annotation: Annotation,
        target_annotation: Annotation,
        /,
    ) -> bool:
        """
        Check if this converter matches for the given object and annotation.

        Checks whether source and target annotations are compatible with this converter,
        taking into account match_source_subtype and match_target_subtype settings.

        :param source_annotation: Annotation of the source object
        :param target_annotation: Target type to convert to
        :return: True if converter matches
        """
        source_match = self.__check_match(
            self._source_annotation, source_annotation, self._match_source_subtype
        )
        target_match = self.__check_match(
            self._target_annotation, target_annotation, self._match_target_subtype
        )
        return source_match and target_match

    def can_convert(
        self,
        obj: SourceT,
        source_annotation: Annotation,
        target_annotation: Annotation,
        /,
    ) -> bool:
        """
        Check if converter can convert the given object. Can be overridden by custom
        subclasses.

        Called internally by the framework after check_match() succeeds.

        :param obj: Object to potentially convert
        :param source_annotation: Annotation of source object
        :param target_annotation: Annotation to convert to
        :return: True if converter can handle conversion
        """
        _ = obj, source_annotation, target_annotation
        return True

    @abstractmethod
    def convert(
        self,
        obj: SourceT,
        source_annotation: Annotation,
        target_annotation: Annotation,
        handle: HandleT,
        /,
    ) -> TargetT:
        """
        Convert object.

        Subclass must define conversion logic. Expected to always succeed since
        check_match() and can_convert() returned True.

        :param obj: Object to convert
        :param source_annotation: Annotation of source object
        :param target_annotation: Annotation to convert to
        :param handle: Handle for conversion operations
        :return: Converted object
        """

    def __check_match(
        self, annotation: Annotation, check_annotation: Annotation, match_subtype: bool
    ) -> bool:
        if match_subtype:
            return check_annotation.is_subtype(annotation)
        else:
            return check_annotation == annotation


class ConverterFuncMixin[SourceT, TargetT, HandleT](ConverterInterface):
    """
    Mixin class for function-based converters.
    """

    _func_wrapper: ConverterFunctionWrapper[SourceT, TargetT, HandleT] | None

    def __init__(
        self,
        source_annotation: Any,
        target_annotation: Any,
        /,
        *,
        func: ConverterFuncType[SourceT, TargetT, HandleT] | None = None,
        match_source_subtype: bool = True,
        match_target_subtype: bool = False,
    ):
        super().__init__(
            source_annotation,
            target_annotation,
            match_source_subtype=match_source_subtype,
            match_target_subtype=match_target_subtype,
        )
        self._func_wrapper = ConverterFunctionWrapper(func) if func else None

    @classmethod
    def from_func(
        cls,
        # TODO: rename: convert_func
        func: ConverterFuncType[SourceT, TargetT, HandleT],
        # TODO: can_convert_func
        /,
        *,
        match_source_subtype: bool = True,
        match_target_subtype: bool = False,
    ) -> Self:
        """
        Create converter from function by inspecting its signature to infer source and
        target types.

        :param func: Converter function
        :param match_source_subtype: Match subtypes of source annotation
        :param match_target_subtype: Match subtypes of target annotation
        :return: Converter instance
        """
        func_wrapper = ConverterFunctionWrapper(func)
        assert func_wrapper.obj_param.annotation
        assert func_wrapper.sig_info.return_annotation

        return cls(
            func_wrapper.obj_param.annotation,
            func_wrapper.sig_info.return_annotation,
            func=func,
            match_source_subtype=match_source_subtype,
            match_target_subtype=match_target_subtype,
        )

    def convert(
        self,
        obj: Any,
        source_annotation: Annotation,
        target_annotation: Annotation,
        handle: HandleT,
        /,
    ) -> Any:
        """
        Convert object using the wrapped function or direct construction.
        """
        _ = source_annotation
        try:
            if func := self._func_wrapper:
                # provided conversion function
                converted_obj = func.invoke(obj, handle)
            else:
                # direct object construction
                concrete_type = cast(
                    Callable[[SourceT], TargetT], target_annotation.concrete_type
                )
                converted_obj = concrete_type(obj)
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"{type(self).__name__} {self} failed to convert {obj} ({type(obj)}): {e}"
            ) from None

        if not target_annotation.is_type(converted_obj):
            raise ValueError(
                f"{type(self).__name__} {self} failed to convert {obj} ({type(obj)}), got {converted_obj} ({type(converted_obj)})"
            )

        return converted_obj


class BaseConverterRegistry[ConverterT: BaseConverter](ABC):
    """
    Base class for converter registries.
    """

    _converters: list[ConverterT]
    """
    List of all converters.
    """

    def __init__(self, *converters: ConverterT):
        self._converters = []
        self.extend(converters)

    def __len__(self) -> int:
        return len(self._converters)

    def find(
        self,
        obj: Any,
        source_annotation: Annotation,
        target_annotation: Annotation,
    ) -> ConverterT | None:
        """
        Find the first converter that can handle the conversion.
        """
        for converter in self._converters:
            if converter.check_match(source_annotation, target_annotation):
                if converter.can_convert(obj, source_annotation, target_annotation):
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

    @abstractmethod
    def _apply_converter(self, converter: Any, obj: Any, frame: FrameT) -> Any:
        """
        Apply a converter to transform the object.
        """
        # TODO:
        # return converter.convert(obj, self._handle_cls(frame))

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
            if converter := registry.find(
                obj, frame.source_annotation, frame.target_annotation
            ):
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

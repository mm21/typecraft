"""
Low-level conversion capability, agnostic of validation vs serialization.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Hashable, Mapping, Sequence, Set
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any, Generator, Self, Sized, cast, overload

from .inspecting.annotations import ANY, Annotation, extract_tuple_args
from .inspecting.classes import extract_type_param
from .inspecting.functions import ParameterInfo, SignatureInfo
from .typedefs import (
    COLLECTION_TARGET_TYPE_EXCEPTIONS,
    COLLECTION_TARGET_TYPES,
    ValueCollectionSourceType,
)

type ConverterFuncType[SourceT, TargetT, FrameT: BaseConversionFrame] = Callable[
    [SourceT], TargetT
] | Callable[[SourceT, FrameT], TargetT]
"""
Function which converts an object. Can take the source object by itself or
source object with info.
"""


class ConverterFunctionWrapper[SourceT, TargetT, FrameT: BaseConversionFrame]:
    """
    Encapsulates a validator or serializer function.
    """

    func: ConverterFuncType[SourceT, TargetT, FrameT]
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

    frame_param: ParameterInfo | None
    """
    Optional parameter for conversion frame, must be positional.
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

        # get frame parameter
        frame_param = sig_info.get_param("frame")
        if frame_param:
            assert (
                frame_param.index == 1
            ), f"Function {func} must take frame as second positional argument, got index {frame_param.index}"

        self.func = func
        self.sig_info = sig_info
        self.obj_param = obj_param
        self.frame_param = frame_param

    def invoke(self, obj: SourceT, frame: FrameT, /) -> TargetT:
        if self.frame_param:
            # invoke with frame
            func = cast(Callable[[SourceT, FrameT], TargetT], self.func)
            return func(obj, frame)
        else:
            # invoke without frame
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
        source_annotation: Annotation | None = None,
        target_annotation: Annotation,
        context: Any | None = None,
    ) -> Any:
        """
        Create a new frame and recurse using the engine.
        """
        source_annotation_ = (
            Annotation(type(obj))
            if source_annotation in (None, ANY)
            else source_annotation
        )
        next_frame = self.copy(
            source_annotation=source_annotation_,
            target_annotation=target_annotation,
            context=context,
            path_append=path_segment,
        )

        # whether to check for cycles: assume hashable == immutable, and only
        # check cycles for mutable objects
        check_cycle = not isinstance(obj, Hashable)

        # recurse and add/remove this object for cycle detection
        if check_cycle:
            if id(obj) in next_frame.seen:
                raise ValueError(f"Already processed object: '{obj}', can't recurse")
            next_frame.seen.add(id(obj))
        next_obj = self.engine.process(obj, next_frame)
        if check_cycle:
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


class ConverterInterface:
    """
    Defines the interface for converters and mixins.
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
        _ = (
            source_annotation,
            target_annotation,
            match_source_subtype,
            match_target_subtype,
        )

    @property
    def _params_str(self) -> str:
        s = f"source={self._source_annotation}"
        t = f"target={self._target_annotation}"
        m_s = f"match_source_subtype={self._match_source_subtype}"
        m_t = f"match_target_subtype={self._match_target_subtype}"
        return ", ".join((s, t, m_s, m_t))


class BaseConverter[SourceT, TargetT, FrameT: BaseConversionFrame](
    ConverterInterface, ABC
):
    """
    Base class for typed converters (validators and serializers).

    Encapsulates common conversion parameters and logic for type-based
    conversion between source and target annotations.
    """

    # TODO: for custom subclass, get annotations using extract_type_param()
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

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._params_str})"

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
            self._target_annotation,
            target_annotation,
            self._match_target_subtype,
            covariant=True,
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
        frame: FrameT,
        /,
    ) -> TargetT:
        """
        Convert object.

        Subclass must define conversion logic. Expected to always succeed since
        check_match() and can_convert() returned True.

        :param obj: Object to convert
        :param source_annotation: Annotation of source object
        :param target_annotation: Annotation to convert to
        :param frame: Frame for conversion operations
        :return: Converted object
        """

    def __check_match(
        self,
        annotation: Annotation,
        check_annotation: Annotation,
        match_subtype: bool,
        covariant: bool = False,
    ) -> bool:
        if covariant and annotation.is_subtype(check_annotation):
            # can match a more specific type (covariant)
            return True
        elif match_subtype and check_annotation.is_subtype(annotation):
            # can match a less specific type (contravariant)
            return True
        else:
            # must match exactly (invariant)
            return annotation == check_annotation


class ConverterFuncMixin[SourceT, TargetT, FrameT: BaseConversionFrame](
    ConverterInterface
):
    """
    Mixin class for function-based converters.
    """

    _func_wrapper: ConverterFunctionWrapper[SourceT, TargetT, FrameT] | None

    @overload
    def __init__(
        self,
        source_annotation: type[SourceT],
        target_annotation: type[TargetT],
        /,
        *,
        func: ConverterFuncType[SourceT, TargetT, FrameT] | None = None,
        match_source_subtype: bool = True,
        match_target_subtype: bool = False,
    ): ...

    @overload
    def __init__(
        self,
        source_annotation: Annotation | Any,
        target_annotation: Annotation | Any,
        /,
        *,
        func: ConverterFuncType[SourceT, TargetT, FrameT] | None = None,
        match_source_subtype: bool = True,
        match_target_subtype: bool = False,
    ): ...

    def __init__(
        self,
        source_annotation: Any,
        target_annotation: Any,
        /,
        *,
        func: ConverterFuncType[SourceT, TargetT, FrameT] | None = None,
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

    def __repr__(self) -> str:
        func = self._func_wrapper.func.__name__ if self._func_wrapper else None
        return f"{type(self).__name__}({self._params_str}, func={func})"

    @classmethod
    def from_func(
        cls,
        # TODO: rename: convert_func
        func: ConverterFuncType[SourceT, TargetT, FrameT],
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
        frame: FrameT,
        /,
    ) -> Any:
        """
        Convert object using the wrapped function or direct construction.
        """
        try:
            if func := self._func_wrapper:
                # provided conversion function
                converted_obj = func.invoke(obj, frame)
            else:
                # direct object construction
                concrete_type = cast(
                    Callable[[SourceT], TargetT], self._target_annotation.concrete_type
                )
                converted_obj = concrete_type(obj)
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"{type(self).__name__} {self} failed to convert {obj} ({type(obj)}): {e}"
            ) from None

        if not frame.target_annotation.is_type(converted_obj):
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


class BaseConversionEngine[
    RegistryT: BaseConverterRegistry,
    FrameT: BaseConversionFrame,
](ABC):
    """
    Base class for conversion engines. Orchestrates conversion process, containing
    common recursion logic with abstract hooks for validation/serialization-specific
    behavior.
    """

    __user_registry: RegistryT
    """
    User-registered converters.
    """

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

    @cached_property
    def __is_serializing(self) -> bool:
        """
        Whether the engine is serializing; for debugging only.
        """
        from .serializing import SerializationEngine

        return isinstance(self, SerializationEngine)

    def process(self, obj: Any, frame: FrameT) -> Any:
        """
        Main conversion dispatcher with common logic.

        Walks the object recursively based on reference annotation,
        invoking type-based converters when conversion is needed.
        """
        if frame.target_annotation.is_union:
            return self._convert_union(obj, frame)

        if frame.source_annotation.is_union:
            return self._convert_source_union(obj, frame)

        # debug asserts: can't convert from any, can't serialize to any
        # - can validate to any; is_type() will just return True
        assert frame.source_annotation != ANY
        if self.__is_serializing:
            assert frame.target_annotation != ANY

        # check if conversion is needed
        if not frame.target_annotation.is_type(obj, recurse=False):
            # find converter and invoke it, returning the converted object
            if converter := self._find_converter(obj, frame):
                return converter.convert(obj, frame)
            raise ValueError(
                f"Object '{obj}' ({type(obj)}) could not be converted from {frame.source_annotation} to {frame.target_annotation}"
            )

        # process collections by recursing into them
        # - we can only create built-in collection types; the user is responsible for
        # recursing into custom subclasses thereof in a custom converter as the
        # custom subclass may have a special construction interface
        if issubclass(
            frame.target_annotation.concrete_type, COLLECTION_TARGET_TYPES
        ) and not issubclass(
            frame.target_annotation.concrete_type, COLLECTION_TARGET_TYPE_EXCEPTIONS
        ):
            return self._process_collection(obj, frame)

        # no conversion needed, return as-is
        return obj

    @abstractmethod
    def _get_builtin_registries(self, frame: FrameT) -> tuple[RegistryT, ...]:
        """
        Get builtin registries to use for conversion based on the parameters.
        """

    def _convert_union(self, obj: Any, frame: FrameT) -> Any:
        """
        Validate constituent types of union by trying each option.
        """
        for ann in frame.target_annotation.arg_annotations:
            try:
                return self.process(obj, frame.copy(target_annotation=ann))
            except (ValueError, TypeError):
                continue
        raise ValueError(
            f"Object '{obj}' ({type(obj)}) could not be converted to any member of union {frame.target_annotation}"
        )

    def _convert_source_union(self, obj: Any, frame: FrameT) -> Any:
        # select which annotation this object matches
        source_annotation = next(
            (a for a in frame.source_annotation.arg_annotations if a.is_type(obj)),
            None,
        )
        assert (
            source_annotation
        ), f"'{obj}' is not a type of union {frame.source_annotation}"
        return self.process(obj, frame.copy(source_annotation=source_annotation))

    def _process_collection(self, obj: Any, frame: FrameT) -> Any:
        """
        Process collection by recursing into items.
        """
        target_type = frame.target_annotation.concrete_type
        assert isinstance(obj, target_type)  # should have gotten converted otherwise

        if issubclass(target_type, tuple):
            return convert_to_tuple(cast(ValueCollectionSourceType, obj), frame)
        elif issubclass(target_type, Sequence):
            return convert_to_sequence(cast(ValueCollectionSourceType, obj), frame)
        elif issubclass(target_type, (set, frozenset)):
            return convert_to_set(cast(ValueCollectionSourceType, obj), frame)
        else:
            assert issubclass(target_type, Mapping)
            return convert_to_mapping(cast(Mapping, obj), frame)

    def _find_converter(self, obj: Any, frame: FrameT) -> BaseConverter | None:
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


def convert_to_tuple(
    obj: ValueCollectionSourceType, frame: BaseConversionFrame
) -> tuple:
    """
    Convert collection to tuple.
    """
    target_type = frame.target_annotation.concrete_type

    # validate variadic tuple: input can't be set
    if (
        len(frame.target_annotation.arg_annotations)
        and frame.target_annotation.arg_annotations[-1].raw is not ...
    ):
        assert not isinstance(
            obj, (set, frozenset)
        ), f"Can't convert from set to fixed-length tuple as items would be in random order: {obj}"

    # ensure object is sized
    sized_obj = list(obj) if isinstance(obj, Generator) else obj

    # extract args from source/target annotations
    source_args = _extract_source_args(sized_obj, frame.source_annotation)
    target_args = extract_tuple_args(frame.target_annotation, length=len(sized_obj))

    if len(sized_obj) != len(target_args):
        raise ValueError(
            f"Tuple length mismatch: expected {len(target_args)} from target annotation, got {len(sized_obj)}: {sized_obj}"
        )

    # create tuple of validated items
    converted_objs = tuple(
        frame.recurse(
            o, i, source_annotation=source_item_ann, target_annotation=target_item_ann
        )
        for i, (o, source_item_ann, target_item_ann) in enumerate(
            zip(sized_obj, source_args, target_args)
        )
    )

    if isinstance(obj, target_type) and all(
        o is v for o, v in zip(obj, converted_objs)
    ):
        # have correct type and no conversions were done; return the original object
        return cast(tuple, obj)
    elif target_type is tuple:
        # have a tuple (not a subclass thereof), return the newly created tuple
        return converted_objs

    raise ValueError(
        f"Cannot construct instance of target type {target_type}; create a custom validator for it"
    )


def convert_to_sequence(
    obj: ValueCollectionSourceType,
    frame: BaseConversionFrame,
    default_target_annotation: Annotation = ANY,
) -> Sequence:
    """
    Convert collection to sequence.
    """
    target_type = frame.target_annotation.concrete_type
    # TODO: check why we need target type of ANY

    # ensure object is sized
    sized_obj = list(obj) if isinstance(obj, Generator) else obj

    # extract args from source/target annotations
    source_args = _extract_source_args(sized_obj, frame.source_annotation)
    target_item_ann = (
        _extract_sequence_item_ann(frame.target_annotation) or default_target_annotation
    )

    # create list of validated items
    converted_objs = [
        frame.recurse(
            o,
            i,
            source_annotation=source_item_ann,
            target_annotation=target_item_ann,
        )
        for i, (o, source_item_ann) in enumerate(zip(sized_obj, source_args))
    ]

    if isinstance(obj, target_type) and all(
        o is n for o, n in zip(sized_obj, converted_objs)
    ):
        # have correct type and no conversions were done; return the original object
        return cast(Sequence, obj)
    elif target_type is list:
        # have a list (not a subclass thereof), return the newly created list
        return converted_objs

    raise ValueError(
        f"Cannot construct instance of target type {target_type}; create a custom validator for it"
    )


def convert_to_set(obj: ValueCollectionSourceType, frame: BaseConversionFrame) -> Set:
    """
    Convert collection to set.
    """
    target_type = frame.target_annotation.concrete_type

    # ensure object is sized
    sized_obj = list(obj) if isinstance(obj, Generator) else obj

    # extract args from source/target annotations
    source_args = _extract_source_args(sized_obj, frame.source_annotation)
    target_item_ann = _extract_sequence_item_ann(frame.target_annotation) or ANY

    # create set of validated items
    converted_objs = {
        frame.recurse(
            o, i, source_annotation=source_item_ann, target_annotation=target_item_ann
        )
        for i, (o, source_item_ann) in enumerate(zip(sized_obj, source_args))
    }

    if isinstance(obj, target_type):
        obj_ids = {id(o) for o in obj}
        if all(id(o) in obj_ids for o in converted_objs):
            # have correct type and no conversions were done; return the original object
            return cast(Set, obj)
    if target_type in (set, frozenset):
        # have a set (not a subclass thereof), return the newly created set
        return converted_objs if target_type is set else frozenset(converted_objs)

    raise ValueError(
        f"Cannot construct instance of target type {target_type}; create a custom validator for it"
    )


def convert_to_mapping(obj: Mapping, frame: BaseConversionFrame) -> Mapping:
    """
    Convert mapping to mapping, which may be of a different type.
    """
    target_type = frame.target_annotation.concrete_type
    source_key_ann, source_value_ann = _extract_mapping_item_ann(
        frame.source_annotation
    ) or (ANY, ANY)
    target_key_ann, target_value_ann = _extract_mapping_item_ann(
        frame.target_annotation
    ) or (ANY, ANY)

    # create dict of validated items
    converted_objs = {
        frame.recurse(
            k,
            f"key[{i}]",
            source_annotation=source_key_ann,
            target_annotation=target_key_ann,
        ): frame.recurse(
            v,
            str(k),
            source_annotation=source_value_ann,
            target_annotation=target_value_ann,
        )
        for i, (k, v) in enumerate(obj.items())
    }

    if isinstance(obj, target_type) and all(
        k_obj is k_conv and obj[k_obj] is converted_objs[k_conv]
        for k_obj, k_conv in zip(obj, converted_objs)
    ):
        # have correct type and no conversions were done; return the original object
        return obj
    elif target_type is dict:
        # have a dict (not a subclass thereof), return the newly created dict
        return converted_objs

    raise ValueError(
        f"Cannot construct instance of target type {target_type}; create a custom validator for it"
    )


def _extract_source_args(
    sized_obj: Sized, source_annotation: Annotation
) -> tuple[Annotation, ...]:
    """
    Extract source item annotations for each element in the collection.

    For tuple sources, expands variadic tuples to match the collection length.
    For other sequences, returns the single item annotation repeated for each element.
    """
    if issubclass(source_annotation.concrete_type, tuple):
        source_args = extract_tuple_args(source_annotation, length=len(sized_obj))
        if len(sized_obj) != len(source_args):
            raise ValueError(
                f"Tuple length mismatch: expected {len(source_args)} from source annotation, got {len(sized_obj)}: {sized_obj}"
            )
        return source_args
    else:
        item_ann = _extract_sequence_item_ann(source_annotation) or ANY
        return tuple([item_ann] * len(sized_obj))


def _extract_sequence_item_ann(ann: Annotation) -> Annotation | None:
    assert (
        len(ann.arg_annotations) <= 1
    ), f"Invalid number of type args for non-mapping collection, must be 0 or 1: {ann}"
    return ann.arg_annotations[0] if len(ann.arg_annotations) == 1 else None


def _extract_mapping_item_ann(ann: Annotation) -> tuple[Annotation, Annotation] | None:
    assert len(ann.arg_annotations) in {
        0,
        2,
    }, f"Invalid number of type args for mapping, must be 0 or 2: {ann}"
    if len(ann.arg_annotations) == 2:
        return ann.arg_annotations
    else:
        return None

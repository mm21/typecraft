"""
Low-level conversion capability, agnostic of validation vs serialization.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Hashable, Mapping, Sequence
from functools import cached_property
from typing import Any, Generator, Iterable, Self, Sized, TypeVar, cast, overload

from .inspecting.annotations import ANY, Annotation, extract_tuple_args
from .inspecting.functions import ParameterInfo, SignatureInfo
from .inspecting.generics import extract_arg, extract_arg_map, extract_args
from .typedefs import (
    COLLECTION_TYPES,
    ValueCollectionType,
)

type FuncConverterType[SourceT, TargetT, FrameT: BaseConversionFrame] = Callable[
    [SourceT], TargetT
] | Callable[[SourceT, FrameT], TargetT]
"""
Function which converts an object. Can take the source object by itself or
source object with info.
"""


class FuncConverterWrapper[SourceT, TargetT, FrameT: BaseConversionFrame]:
    """
    Encapsulates a validator or serializer function.
    """

    func: FuncConverterType[SourceT, TargetT, FrameT]
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
        frame_param = next(
            sig_info.get_params(annotation=BaseConversionFrame, positional=True), None
        )
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
    User context passed at validation/serialization entry point.
    """

    params: ParamsT
    """
    Parameters passed at validation/serialization entry point.
    """

    __engine: BaseConversionEngine
    """
    Conversion engine for recursion.
    """

    __path: tuple[str | int, ...]
    """
    Field path at this level in recursion.
    """

    __seen: set[int]
    """
    Object ids for cycle detection.
    """

    def __init__(
        self,
        *,
        source_annotation: Annotation,
        target_annotation: Annotation,
        context: Any,
        params: ParamsT,
        engine: BaseConversionEngine,
        path: tuple[str | int, ...] | None = None,
        seen: set[int] | None = None,
    ):
        self.source_annotation = source_annotation
        self.target_annotation = target_annotation
        self.context = context
        self.params = params
        self.__engine = engine
        self.__path = path or ()
        self.__seen = seen or set()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(source={self.source_annotation}, target={self.target_annotation})"

    def recurse(
        self,
        obj: Any,
        path_segment: str | int,
        /,
        *,
        source_annotation: Annotation | None = None,
        target_annotation: Annotation,
        context: Any = ...,
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
            if id(obj) in next_frame.__seen:
                raise ValueError(f"Already processed object: '{obj}', can't recurse")
            next_frame.__seen.add(id(obj))
        next_obj = self.__engine.process(obj, next_frame)
        if check_cycle:
            next_frame.__seen.remove(id(obj))

        return next_obj

    def copy(
        self,
        *,
        source_annotation: Annotation | None = None,
        target_annotation: Annotation | None = None,
        context: Any = ...,
        path_append: str | int | None = None,
    ) -> Self:
        """
        Create a new frame with the arguments replaced if not None.
        """
        path = (
            self.__path
            if path_append is None
            else tuple(list(self.__path) + [path_append])
        )
        return type(self)(
            source_annotation=source_annotation or self.source_annotation,
            target_annotation=target_annotation or self.target_annotation,
            context=context if context is not ... else self.context,
            params=self.params,
            engine=self.__engine,
            path=path,
            seen=self.__seen,
        )


class ConverterInterface[SourceT, TargetT, FrameT: BaseConversionFrame](ABC):
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
        *,
        match_source_subtype: bool,
        match_target_subtype: bool,
    ):
        _ = (
            match_source_subtype,
            match_target_subtype,
        )
        ...

    @property
    def _params_str(self) -> str:
        s = f"source={self._source_annotation.raw}"
        t = f"target={self._target_annotation.raw}"
        m_s = f"match_source_subtype={self._match_source_subtype}"
        m_t = f"match_target_subtype={self._match_target_subtype}"
        return ", ".join((s, t, m_s, m_t))

    def can_convert(
        self,
        obj: SourceT,
        source_annotation: Annotation,
        target_annotation: Annotation,
        /,
    ) -> bool:
        """
        Can be overridden by custom subclasses. Check if converter can convert the
        given object.

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


class BaseConverter[SourceT, TargetT, FrameT: BaseConversionFrame](
    ConverterInterface[SourceT, TargetT, FrameT], ABC
):
    """
    Base class for typed converters (validators and serializers).

    Encapsulates common conversion parameters and logic for type-based
    conversion between source and target annotations.
    """

    def __init__(
        self,
        *,
        match_source_subtype: bool = True,
        match_target_subtype: bool = False,
    ):
        self._source_annotation, self._target_annotation = self._get_annotations()
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
        if not self.__check_match(
            self._source_annotation, source_annotation, self._match_source_subtype
        ):
            return False
        if not self.__check_match(
            self._target_annotation,
            target_annotation,
            self._match_target_subtype,
            covariant=True,
        ):
            return False
        return True

    @abstractmethod
    def _get_annotations(self) -> tuple[Annotation, Annotation]:
        """
        Get source and target annotations.
        """

    def _check_convert(
        self, obj: Any, source_annotation: Annotation, target_annotation: Annotation
    ) -> bool:
        """
        Check if this converter can convert this object.
        """
        # check if source/target matches
        if not self.check_match(source_annotation, target_annotation):
            return False
        # check if object matches supported source annotation
        if not self._source_annotation.is_type(obj):
            return False
        # check if converter can convert this specific object
        if not self.can_convert(obj, source_annotation, target_annotation):
            return False
        return True

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


class FuncConverterMixin[SourceT, TargetT, FrameT: BaseConversionFrame](
    ConverterInterface[SourceT, TargetT, FrameT]
):
    """
    Mixin class for function-based converters.
    """

    __source_annotation: Annotation
    __target_annotation: Annotation
    __func_wrapper: FuncConverterWrapper[SourceT, TargetT, FrameT] | None
    __predicate_func: Callable[[SourceT], bool] | None

    @overload
    def __init__(
        self,
        source_annotation: type[SourceT],
        target_annotation: type[TargetT],
        /,
        *,
        func: FuncConverterType[SourceT, TargetT, FrameT] | None = None,
        predicate_func: Callable[[SourceT], bool] | None = None,
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
        func: FuncConverterType[SourceT, TargetT, FrameT] | None = None,
        predicate_func: Callable[[SourceT], bool] | None = None,
        match_source_subtype: bool = True,
        match_target_subtype: bool = False,
    ): ...

    def __init__(
        self,
        source_annotation: Any,
        target_annotation: Any,
        /,
        *,
        func: FuncConverterType[SourceT, TargetT, FrameT] | None = None,
        predicate_func: Callable[[SourceT], bool] | None = None,
        match_source_subtype: bool = True,
        match_target_subtype: bool = False,
    ):
        self.__source_annotation = Annotation._normalize(source_annotation)
        self.__target_annotation = Annotation._normalize(target_annotation)
        super().__init__(
            match_source_subtype=match_source_subtype,
            match_target_subtype=match_target_subtype,
        )
        self.__func_wrapper = FuncConverterWrapper(func) if func else None
        self.__predicate_func = predicate_func

    def __repr__(self) -> str:
        func = self.__func_wrapper.func if self.__func_wrapper else None
        predicate_func = self.__predicate_func
        return f"{type(self).__name__}({self._params_str}, func={func}, predicate_func={predicate_func})"

    @classmethod
    def from_func(
        cls,
        func: FuncConverterType[SourceT, TargetT, FrameT],
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
        func_wrapper = FuncConverterWrapper(func)
        assert func_wrapper.obj_param.annotation
        assert func_wrapper.sig_info.return_annotation

        return cls(
            func_wrapper.obj_param.annotation,
            func_wrapper.sig_info.return_annotation,
            func=func,
            match_source_subtype=match_source_subtype,
            match_target_subtype=match_target_subtype,
        )

    def can_convert(
        self,
        obj: SourceT,
        source_annotation: Annotation,
        target_annotation: Annotation,
        /,
    ) -> bool:
        if predicate_func := self.__predicate_func:
            predicate = predicate_func(obj)
        else:
            predicate = True
        return predicate and super().can_convert(
            obj, source_annotation, target_annotation
        )

    def convert(
        self,
        obj: SourceT,
        frame: FrameT,
        /,
    ) -> TargetT:
        """
        Convert object using the wrapped function or direct construction.
        """
        source_type = self._source_annotation.concrete_type
        target_type = self._target_annotation.concrete_type

        try:
            if func := self.__func_wrapper:
                # provided conversion function
                converted_obj = func.invoke(obj, frame)
            else:
                # direct object construction

                # handle conversion to subtypes of builtin collections
                if issubclass(source_type, Mapping) and issubclass(target_type, dict):
                    assert isinstance(obj, Mapping)
                    converted_obj = convert_to_dict(obj, frame, construct=True)
                elif issubclass(source_type, Iterable) and issubclass(
                    target_type, (list, tuple, set, frozenset)
                ):
                    assert isinstance(obj, Iterable)
                    if issubclass(target_type, list):
                        converted_obj = convert_to_list(obj, frame, construct=True)
                    elif issubclass(target_type, tuple):
                        converted_obj = convert_to_tuple(obj, frame, construct=True)
                    else:
                        converted_obj = convert_to_set(obj, frame, construct=True)
                else:
                    # not a builtin collection, attempt to construct without recursion
                    callable = cast(Callable[[SourceT], TargetT], target_type)
                    converted_obj = callable(obj)
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"{type(self).__name__} {self} failed to convert {obj} ({type(obj)}): {e}"
            )

        # ensure conversion succeeded
        if not isinstance(converted_obj, target_type):
            raise ValueError(
                f"{type(self).__name__} {self} failed to convert {obj} ({type(obj)}), got {converted_obj} ({type(converted_obj)})"
            )

        # can be an expensive check
        assert frame.target_annotation.is_type(converted_obj)

        return cast(TargetT, converted_obj)

    def _get_annotations(self) -> tuple[Annotation, Annotation]:
        return self.__source_annotation, self.__target_annotation


class GenericConverterMixin:
    """
    Mixin class for extracting source/destination types from type parameters.
    """

    def _get_annotations(self) -> tuple[Annotation, Annotation]:
        # get annotations from type params
        arg_map = extract_arg_map(type(self), BaseConverter)
        source_type = arg_map.get("SourceT")
        target_type = arg_map.get("TargetT")
        if not (source_type and target_type):
            raise TypeError(
                f"Converter class {type(self)} must be parameterized with source and target types"
            )

        if isinstance(source_type, TypeVar) or isinstance(target_type, TypeVar):
            raise TypeError(
                f"Converter class {type(self)} cannot have unresolved TypeVars: got SourceT={source_type}, TargetT={target_type}"
            )

        return Annotation(source_type), Annotation(target_type)


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
        assert not target_annotation.is_union
        for converter in self._converters:
            if converter._check_convert(obj, source_annotation, target_annotation):
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
        converter_cls = extract_arg(
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

    def process(self, obj: Any, frame: FrameT) -> Any:
        """
        Main conversion dispatcher with common logic.

        Walks the object recursively based on reference annotation,
        invoking type-based converters when conversion is needed.
        """
        # if source is a union, select which specific annotation matches the object
        if frame.source_annotation.is_union:
            frame_ = frame.copy(
                source_annotation=_select_ann_from_union(obj, frame.source_annotation)
            )
        else:
            frame_ = frame

        # debug asserts:
        # - can't validate/serialize FROM any: need to know the object type
        # - can't serialize TO any: must have a known supported target type
        # - can validate TO any: is_type() will just return True
        assert frame_.source_annotation != ANY
        if self.__is_serializing:
            assert frame_.target_annotation != ANY

        # invoke conversion if needed
        if not frame_.target_annotation.is_type(obj, recurse=False):
            return self._invoke_conversion(obj, frame_)

        # if target is a union, select which specific annotation matches the object
        if frame_.target_annotation.is_union:
            frame_ = frame_.copy(
                target_annotation=_select_ann_from_union(obj, frame_.target_annotation)
            )

        # process collections by recursing into them
        if issubclass(frame_.target_annotation.concrete_type, COLLECTION_TYPES):
            return self._process_collection(obj, frame_)

        # no conversion needed, return as-is
        return obj

    @abstractmethod
    def _get_builtin_registries(self, frame: FrameT) -> tuple[RegistryT, ...]:
        """
        Get builtin registries to use for conversion based on the parameters.
        """

    def _process_collection(self, obj: Any, frame: FrameT) -> Any:
        """
        Process collection by recursing into items.

        We can only create built-in collection types; the user is responsible for
        recursing into custom subclasses thereof in a custom converter as the
        custom subclass may have a special construction interface.
        """
        target_type = frame.target_annotation.concrete_type
        assert isinstance(obj, target_type)  # should have gotten converted otherwise

        if issubclass(target_type, list):
            return convert_to_list(cast(ValueCollectionType, obj), frame)
        elif issubclass(target_type, tuple):
            return convert_to_tuple(cast(ValueCollectionType, obj), frame)
        elif issubclass(target_type, (set, frozenset)):
            return convert_to_set(cast(ValueCollectionType, obj), frame)
        else:
            assert issubclass(target_type, dict)
            return convert_to_dict(cast(Mapping, obj), frame)

    def _invoke_conversion(self, obj: Any, frame: FrameT) -> Any:
        if frame.target_annotation.is_union:
            # handle union
            for target_option in frame.target_annotation.arg_annotations:
                if converter := self._find_converter(obj, frame, target_option):
                    frame_ = frame.copy(target_annotation=target_option)
                    try:
                        return converter.convert(obj, frame_)
                    except (ValueError, TypeError):
                        # keep trying other converters
                        continue
        else:
            # handle single target type
            if converter := self._find_converter(obj, frame, frame.target_annotation):
                return converter.convert(obj, frame)
        raise ValueError(
            f"Object '{obj}' ({type(obj)}) could not be converted from {frame.source_annotation} to {frame.target_annotation}"
        )

    def _find_converter(
        self, obj: Any, frame: FrameT, target_annotation: Annotation
    ) -> BaseConverter | None:
        for registry in (self.__user_registry, *self._get_builtin_registries(frame)):
            if converter := registry.find(
                obj, frame.source_annotation, target_annotation
            ):
                return converter
        return None

    @property
    def __registry_cls(self) -> type[RegistryT]:
        registry_cls = extract_arg(
            type(self), BaseConversionEngine, "RegistryT", BaseConverterRegistry
        )
        return cast(type[RegistryT], registry_cls)

    @cached_property
    def __is_serializing(self) -> bool:
        """
        Whether the engine is serializing; for debugging only.
        """
        from .serializing import SerializationEngine

        return isinstance(self, SerializationEngine)


def convert_to_list(
    obj: Iterable, frame: BaseConversionFrame, /, *, construct: bool = False
) -> list:
    """
    Convert collection to list.
    """
    target_type = frame.target_annotation.concrete_type
    assert issubclass(target_type, list)

    sized_obj = obj if isinstance(obj, Sized) else list(obj)

    # extract item annotations
    source_item_anns = _extract_value_item_anns(sized_obj, frame.source_annotation)
    target_item_ann = _extract_value_item_ann(frame.target_annotation, list)

    # create list of validated items
    converted_objs = [
        frame.recurse(
            o,
            i,
            source_annotation=(
                source_item_anns[i]
                if isinstance(source_item_anns, tuple)
                else source_item_anns
            ),
            target_annotation=target_item_ann,
        )
        for i, o in enumerate(sized_obj)
    ]

    if isinstance(obj, target_type) and all(
        o is n for o, n in zip(sized_obj, converted_objs)
    ):
        # have correct type and no conversions were done; return the original object
        return obj
    elif target_type is list:
        # have a list (not a subclass thereof), return the newly created list
        return converted_objs
    elif construct:
        return target_type(converted_objs)

    raise ValueError(
        f"Cannot construct instance of target type {target_type}; create a custom validator for it"
    )


def convert_to_tuple(
    obj: Iterable, frame: BaseConversionFrame, /, *, construct: bool = False
) -> tuple:
    """
    Convert collection to tuple.
    """
    target_type = frame.target_annotation.concrete_type
    assert issubclass(target_type, tuple)

    # validate non-variadic tuple: input can't be set
    if (
        len(frame.target_annotation.arg_annotations)
        and frame.target_annotation.arg_annotations[-1].raw is not ...
    ):
        if isinstance(obj, (set, frozenset)):
            raise ValueError(
                f"Can't convert from set to fixed-length tuple as items would be in random order: {obj}"
            )

    sized_obj = obj if isinstance(obj, Sized) else list(obj)

    # extract item annotations
    source_item_anns = _extract_value_item_anns(sized_obj, frame.source_annotation)
    target_item_anns = extract_tuple_args(frame.target_annotation)

    if isinstance(target_item_anns, tuple) and len(target_item_anns) != len(sized_obj):
        raise ValueError(
            f"Tuple length mismatch: expected {len(target_item_anns)} from target annotation {frame.target_annotation}, got {len(sized_obj)}: {sized_obj}"
        )

    # create tuple of validated items
    converted_objs = tuple(
        frame.recurse(
            o,
            i,
            source_annotation=(
                source_item_anns[i]
                if isinstance(source_item_anns, tuple)
                else source_item_anns
            ),
            target_annotation=(
                target_item_anns[i]
                if isinstance(target_item_anns, tuple)
                else target_item_anns
            ),
        )
        for i, o, in enumerate(sized_obj)
    )

    if isinstance(obj, target_type) and all(
        o is v for o, v in zip(sized_obj, converted_objs)
    ):
        # have correct type and no conversions were done; return the original object
        return obj
    elif target_type is tuple:
        # have a tuple (not a subclass thereof), return the newly created tuple
        return converted_objs
    elif construct:
        return target_type(converted_objs)

    raise ValueError(
        f"Cannot construct instance of target type {target_type}; create a custom validator for it"
    )


def convert_to_set(
    obj: Iterable, frame: BaseConversionFrame, /, *, construct: bool = False
) -> set | frozenset:
    """
    Convert collection to set.
    """
    target_type = frame.target_annotation.concrete_type
    assert issubclass(target_type, (set, frozenset))

    sized_obj = obj if isinstance(obj, Sized) else list(obj)

    # extract item annotations
    source_item_anns = _extract_value_item_anns(sized_obj, frame.source_annotation)
    target_item_ann = _extract_value_item_ann(frame.target_annotation, set)

    # create set of validated items
    converted_objs = {
        frame.recurse(
            o,
            i,
            source_annotation=(
                source_item_anns[i]
                if isinstance(source_item_anns, tuple)
                else source_item_anns
            ),
            target_annotation=target_item_ann,
        )
        for i, o in enumerate(sized_obj)
    }

    if isinstance(obj, target_type):
        obj_ids = {id(o) for o in sized_obj}
        if all(id(o) in obj_ids for o in converted_objs):
            # have correct type and no conversions were done; return the original object
            return obj
    if target_type in (set, frozenset):
        # have a set (not a subclass thereof), return the newly created set
        return converted_objs if target_type is set else frozenset(converted_objs)
    elif construct:
        return target_type(converted_objs)

    raise ValueError(
        f"Cannot construct instance of target type {target_type}; create a custom validator for it"
    )


def convert_to_dict(
    obj: Mapping, frame: BaseConversionFrame, /, *, construct: bool = False
) -> dict:
    """
    Convert mapping to dict.
    """
    target_type = frame.target_annotation.concrete_type
    assert issubclass(target_type, dict)

    # extract item annotations
    source_key_ann, source_value_ann = _extract_mapping_item_ann(
        frame.source_annotation, default=ANY
    )
    target_key_ann, target_value_ann = _extract_mapping_item_ann(
        frame.target_annotation
    )

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
    elif construct:
        return target_type(converted_objs)

    raise ValueError(
        f"Cannot construct instance of target type {target_type}; create a custom validator for it"
    )


def _extract_value_item_anns(
    obj: Sized, ann: Annotation
) -> Annotation | tuple[Annotation, ...]:
    """
    Extract item annotations for each element in the collection.

    - Returns `Annotation` if the annotation applies to each item in obj
    - Returns `tuple[Annotation, ...]` if obj is a fixed-length tuple
    """
    if issubclass(ann.concrete_type, tuple):
        source_args = extract_tuple_args(ann)
        if isinstance(source_args, tuple) and len(obj) != len(source_args):
            raise ValueError(
                f"Tuple length mismatch: expected {len(source_args)} from annotation {ann}, got {len(obj)}: {obj}"
            )
        return source_args
    else:
        # determine which collection type this is a subclass of
        collection_cls = next(
            (t for t in COLLECTION_TYPES if issubclass(ann.concrete_type, t)), None
        )
        assert collection_cls
        return _extract_value_item_ann(ann, collection_cls, default=ANY)


def _extract_value_item_ann(
    ann: Annotation, base_cls: type, default: Annotation | None = None
) -> Annotation:
    """
    Extract item annotation for non-tuple value collection.
    """
    # handle special cases
    if issubclass(ann.concrete_type, Generator):
        return ann.arg_annotations[0] if len(ann.arg_annotations) else ANY
    if issubclass(ann.concrete_type, range):
        return Annotation(int)

    # extract item annotation from collection
    args = extract_args(ann.raw, base_cls)
    assert len(args) <= 1

    if len(args) == 1:
        return Annotation(args[0])

    if default:
        return default

    raise TypeError(f"Could not find item annotation of collection {ann}")


def _extract_mapping_item_ann(
    ann: Annotation, default: Annotation | None = None
) -> tuple[Annotation, Annotation]:
    """
    Extract item annotations as (key annotation, value annotation) for mapping
    collection.
    """
    args = extract_args(ann.raw, dict)
    assert len(args) in {0, 2}

    if len(args) == 2:
        return Annotation(args[0]), Annotation(args[1])

    if default:
        return default, default

    raise TypeError(f"Could not find item annotation of dict {ann}")


def _select_ann_from_union(obj: Any, union: Annotation) -> Annotation:
    """
    Select the annotation from the union which matches the given object.
    """
    assert union.is_union
    ann = next(
        (a for a in union.arg_annotations if a.is_type(obj, recurse=False)),
        None,
    )
    if not ann:
        raise ValueError(f"'{obj}' ({type(obj)}) is not a type of union {union}")
    if ann.is_union:
        return _select_ann_from_union(obj, ann)
    return ann

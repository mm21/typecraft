from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Any, Self, cast

from ..exceptions import ConversionErrorDetail
from ..inspecting.annotations import ANY, Annotation
from ..inspecting.functions import ParameterInfo, SignatureInfo
from ..inspecting.generics import extract_arg
from ._types import ERROR_SENTINEL

if TYPE_CHECKING:
    from .engine import BaseConversionEngine


__all__ = [
    "MatchSpec",
    "BaseConverter",
    "BaseConverterRegistry",
]


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

    params: ParamsT
    """
    Parameters passed at validation/serialization entry point.
    """

    context: Any | None
    """
    User context passed at validation/serialization entry point. Can be overridden
    when recursing into the next frame.
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

    __errors: list[ConversionErrorDetail]
    """
    Shared list for collecting conversion errors.
    """

    def __init__(
        self,
        *,
        source_annotation: Annotation,
        target_annotation: Annotation,
        params: ParamsT,
        context: Any | None,
        engine: BaseConversionEngine,
        path: tuple[str | int, ...] | None = None,
        seen: set[int] | None = None,
        errors: list[ConversionErrorDetail] | None = None,
    ):
        self.source_annotation = source_annotation
        self.target_annotation = target_annotation
        self.context = context
        self.params = params
        self.__engine = engine
        self.__path = path or ()
        self.__seen = seen or set()
        self.__errors = errors if errors is not None else []

    def __repr__(self) -> str:
        return f"{type(self).__name__}(source={self.source_annotation}, target={self.target_annotation})"

    @property
    def path(self) -> tuple[str | int, ...]:
        """
        The current path in the object tree.
        """
        return self.__path

    @property
    def errors(self) -> list[ConversionErrorDetail]:
        """
        The shared error list for this conversion invocation.
        """
        return self.__errors

    def recurse(
        self,
        obj: Any,
        path_segment: str | int,
        /,
        *,
        source_annotation: Annotation | None = None,
        target_annotation: Annotation,
        context: Any | None = ...,
    ) -> Any:
        """
        Create a new frame and recurse using the engine. `context` is replaced if not
        `...`; otherwise it's passed through unchanged.
        """
        if self.__engine._is_validating:
            # validating: get actual object type
            # - could be converting from e.g. a subclass of list[int], in which
            # case source item annotation would always be int
            source_annotation_ = Annotation(type(obj))
        else:
            # serializing: get actual object type only if not passed
            # - if passed, it may contain a specific annotation to match a serializer
            source_annotation_ = (
                Annotation(type(obj))
                if source_annotation in (None, ANY)
                else source_annotation
            )

        next_frame = self._copy(
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
                exception = ValueError(
                    f"Already processed object: '{obj}', can't recurse"
                )
                next_frame.append_error(obj, exception)
                return ERROR_SENTINEL
            next_frame.__seen.add(id(obj))
        next_obj = self.__engine.process(obj, next_frame)
        if check_cycle:
            next_frame.__seen.remove(id(obj))

        return next_obj

    def append_error(self, obj: Any, exception: Exception):
        """
        Append a conversion error to the shared error list.
        """
        self.__errors.append(ConversionErrorDetail(obj, self, exception))

    def _copy(
        self,
        *,
        source_annotation: Annotation | None = None,
        target_annotation: Annotation | None = None,
        context: Any | None = ...,
        path_append: str | int | None = None,
    ) -> Self:
        """
        Create a new frame with the arguments replaced if not `None`, except `context`
        which is replaced if not `...`.
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
            errors=self.__errors,
        )

    @classmethod
    def _setup(
        cls,
        *,
        obj: Any,
        source_type: Annotation | Any | None,
        target_type: Annotation | Any,
        params: Any | None,
        default_params: Any,
        context: Any | None,
        engine: BaseConversionEngine,
    ) -> Self:
        """
        Create initial frame at conversion entry point.
        """
        source_annotation = (
            Annotation._normalize(source_type)
            if source_type is not None
            else Annotation(type(obj))
        )
        target_annotation = Annotation._normalize(target_type)
        return cls(
            source_annotation=source_annotation,
            target_annotation=target_annotation,
            params=params if params is not None else default_params,
            context=context,
            engine=engine,
        )


@dataclass
class MatchSpec:
    """
    Match specification: specifies how to match source/target annotations for a
    converter.
    """

    assignable_from_source: bool = True
    """
    Whether to match when the converter's source type is assignable from the requested
    source type. Essentially asks:

    - "If I convert from `Animal`, can I also handle a request to convert from `Dog`?"
    - "If I convert from `int | str`, can I also handle a request to convert from `int`?

    This should generally be true as it describes regular subtype polymorphism.
    """

    assignable_from_target: bool = False
    """
    Whether to match when the converter's target type is assignable from the requested
    target type. Essentially asks:

    - "If I convert to `Animal`, can I also handle a request to convert to `Dog`?"
    - "If I convert to `int | str`, can I also handle a request to convert to `int`?
    
    If `True`, the converter must produce the specific requested target type passed
    during conversion.
    """

    assignable_to_target: bool = True
    """
    Whether to match when the converter's target type is assignable to the requested
    target type. Essentially asks:
    
    - "If I convert to `Dog`, can I also handle a request to convert to `Animal`?"
    - "If I convert to `int`, can I also handle a request to convert to `int | str`?
    - "If I convert to `bool`, can I also handle a request to convert to `int`?

    Set to `False` for converters with specific semantic requirements. For example,
    it may be unexpected to convert to `int` and get a `bool` even though the type
    is technically satisfied.
    """


class ConverterInterface[SourceT, TargetT, FrameT: BaseConversionFrame](ABC):
    """
    Defines the interface for converters and mixins.
    """

    match_spec: MatchSpec = MatchSpec()
    """
    Specification of matching behavior.
    """

    _source_annotation: Annotation
    """
    Annotation specifying type to convert from.
    """

    _target_annotation: Annotation
    """
    Annotation specifying type to convert to.
    """

    def __init__(
        self,
        *,
        match_spec: MatchSpec | None,
    ):
        if match_spec:
            self.match_spec = match_spec

    @property
    def _params_str(self) -> str:
        return f"{self._source_annotation.raw} -> {self._target_annotation.raw}"

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

    @abstractmethod
    def _get_annotations(self) -> tuple[Annotation, Annotation]:
        """
        Get source and target annotations.
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
        match_spec: MatchSpec | None = None,
    ):
        super().__init__(match_spec=match_spec)
        self._source_annotation, self._target_annotation = self._get_annotations()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._params_str})"

    @property
    def source_annotation(self) -> Annotation:
        return self._source_annotation

    @property
    def target_annotation(self) -> Annotation:
        return self._target_annotation

    def check_match(
        self,
        source_annotation: Annotation,
        target_annotation: Annotation,
        /,
    ) -> bool:
        """
        Check if this converter matches the given annotation.

        :param source_annotation: Type to convert from
        :param target_annotation: Type to convert to
        :return: True if converter matches
        """
        # TODO: add test for match_source_subtype=False: int source type, ensure can't
        # convert bool source
        if not self.__check_match(
            self._source_annotation,
            source_annotation,
            assignable_from=self.match_spec.assignable_from_source,
            assignable_to=False,
        ):
            return False

        # try all possible target annotations in case of union
        # - if assignable_from_target is True, only one union member needs to match
        # - otherwise, all union members must match requested target: we don't know
        #   which one the converter will return
        target_annotations = (
            self._target_annotation.arg_annotations
            if self._target_annotation.is_union
            else (self._target_annotation,)
        )

        # check whether we're producing a union and only one member needs to match
        # (converter must produce the requested type)
        match_any_union = (
            self._target_annotation.is_union and self.match_spec.assignable_from_target
        )

        # check each target annotation
        for ann in target_annotations:
            if self.__check_match(
                ann,
                target_annotation,
                assignable_from=self.match_spec.assignable_from_target,
                assignable_to=self.match_spec.assignable_to_target,
            ):
                if match_any_union:
                    return True
            else:
                if match_any_union:
                    continue
                return False

        return True if not match_any_union else False

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
        if not self._source_annotation.check_instance(obj):
            return False
        # check if converter can convert this specific object
        if not self.can_convert(obj, source_annotation, target_annotation):
            return False
        return True

    def __check_match(
        self,
        my_annotation: Annotation,
        requested_annotation: Annotation,
        *,
        assignable_from: bool,
        assignable_to: bool,
    ) -> bool:
        if assignable_from and requested_annotation.is_assignable(my_annotation):
            # match a more specific type, e.g. `Animal -> Dog`
            return True
        elif assignable_to and my_annotation.is_assignable(requested_annotation):
            # match a more general type, e.g. `int -> int | str`
            return True
        else:
            # must match exactly, but allow match against Any
            return my_annotation.equals(requested_annotation, match_any=True)


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

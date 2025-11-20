from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Hashable, Sequence
from functools import cached_property
from typing import TYPE_CHECKING, Any, Self, cast

from ..inspecting.annotations import ANY, Annotation
from ..inspecting.functions import ParameterInfo, SignatureInfo
from ..inspecting.generics import extract_arg

if TYPE_CHECKING:
    from .engine import BaseConversionEngine

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
        context: Any | None = ...,
    ) -> Any:
        """
        Create a new frame and recurse using the engine. `context` is replaced if not
        `...`; otherwise it's passed through unchanged.
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


class ConverterInterface[SourceT, TargetT, FrameT: BaseConversionFrame](ABC):
    """
    Defines the interface for converters and mixins.
    """

    match_source_subtype: bool = True
    """
    Whether to match subtypes of the source annotation.
    """

    match_target_subtype: bool = False
    """
    Whether to match subtypes of the target annotation.
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
        match_source_subtype: bool | None,
        match_target_subtype: bool | None,
    ):
        if match_source_subtype is not None:
            self.match_source_subtype = match_source_subtype
        if match_target_subtype is not None:
            self.match_target_subtype = match_target_subtype

    @property
    def _params_str(self) -> str:
        s = f"source={self._source_annotation.raw}"
        t = f"target={self._target_annotation.raw}"
        m_s = f"match_source_subtype={self.match_source_subtype}"
        m_t = f"match_target_subtype={self.match_target_subtype}"
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
        match_source_subtype: bool | None = None,
        match_target_subtype: bool | None = None,
    ):
        super().__init__(
            match_source_subtype=match_source_subtype,
            match_target_subtype=match_target_subtype,
        )
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
        Check if this converter matches for the given object and annotation.

        Checks whether source and target annotations are compatible with this converter,
        taking into account `match_source_subtype` and `match_target_subtype` settings.

        :param source_annotation: Annotation of the source object
        :param target_annotation: Target type to convert to
        :return: True if converter matches
        """
        if not self.__check_match(
            self._source_annotation, source_annotation, self.match_source_subtype
        ):
            return False
        if not self.__check_match(
            self._target_annotation,
            target_annotation,
            self.match_target_subtype,
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
        if not self._source_annotation.check_instance(obj):
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

from __future__ import annotations

from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Self, cast

from ...exceptions import ConversionErrorDetail
from ...inspecting.annotations import ANY, Annotation
from ...inspecting.functions import ParameterInfo, SignatureInfo
from ...inspecting.generics import extract_arg
from .._types import ERROR_SENTINEL

if TYPE_CHECKING:
    from ..engine import BaseConversionEngine


type FuncConverterType[SourceT, TargetT, FrameT: BaseConversionFrame] = Callable[
    [SourceT], TargetT
] | Callable[[SourceT, FrameT], TargetT]
"""
Function which converts an object.

Can take the source object by itself or source object with frame for recursion or
parameter access.
"""


@dataclass(kw_only=True)
class BaseConversionParams:
    """
    Common params passed by user.
    """

    by_alias: bool = False
    """
    Whether to validate/serialize models by alias.
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

        args = sig_info.get_params(positional=True)

        # get object parameter
        assert len(
            args
        ), f"Function {func} does not take any positional params, must take obj as positional"
        obj_param = args[0]

        if len(args) > 1:
            frame_param = args[1]
            if frame_param.annotation:
                assert issubclass(
                    frame_param.annotation.concrete_type, BaseConversionFrame
                )
        else:
            frame_param = None

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


class BaseConversionFrame[ParamsT: BaseConversionParams]:

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
    User context passed at validation/serialization entry point.

    Can be overridden when recursing into the next frame.
    """

    _seen: set[int]
    """
    Object ids for cycle detection.
    """

    __params_cls: type[ParamsT]
    """
    Params class extracted from type arg.
    """

    __engine: BaseConversionEngine | None = None
    """
    Conversion engine for recursion.
    """

    __path: tuple[str | int, ...]
    """
    Field path at this level in recursion.
    """

    __errors: list[ConversionErrorDetail]
    """
    Shared list for collecting conversion errors.
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.__params_cls = cast(
            type[ParamsT],
            extract_arg(cls, BaseConversionFrame, "ParamsT", BaseConversionParams),
        )

    def __init__(
        self,
        *,
        source_annotation: Annotation,
        target_annotation: Annotation,
        params: ParamsT | None,
        context: Any | None,
        engine: BaseConversionEngine | None = None,
        path: tuple[str | int, ...] | None = None,
        seen: set[int] | None = None,
        errors: list[ConversionErrorDetail] | None = None,
    ):
        self.source_annotation = source_annotation
        self.target_annotation = target_annotation
        self.context = context
        self.params = params or type(self).__params_cls()
        self._seen = seen or set()
        self.__engine = engine
        self.__path = path or ()
        self.__errors = errors if errors is not None else []

    def __repr__(self) -> str:
        return "{}(source={}, target={}, path={})".format(
            type(self).__name__,
            self.source_annotation,
            self.target_annotation,
            self.path,
        )

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
        Create a new frame and recurse using the engine.

        `context` is replaced if not `...`; otherwise it's passed through unchanged.
        """
        assert self.__engine

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
            if id(obj) in next_frame._seen:
                exception = ValueError(
                    f"Already processed object: '{obj}', can't recurse"
                )
                next_frame.append_error(obj, exception)
                return ERROR_SENTINEL
            next_frame._seen.add(id(obj))
        next_obj = self.__engine.process(obj, next_frame)
        if check_cycle:
            next_frame._seen.remove(id(obj))

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
        path_prepend: str | int | None = None,
    ) -> Self:
        """
        Create a new frame with the arguments replaced if not `None`, except `context`
        which is replaced if not `...`.
        """
        # adjust path if needed
        if not (path_append is None and path_prepend is None):
            path_segments: list[str | int] = []
            if path_prepend is not None:
                path_segments.append(path_prepend)
            path_segments += list(self.__path)
            if path_append is not None:
                path_segments.append(path_append)
            path = tuple(path_segments)
        else:
            path = self.__path

        return type(self)(
            source_annotation=source_annotation or self.source_annotation,
            target_annotation=target_annotation or self.target_annotation,
            params=self.params,
            context=context if context is not ... else self.context,
            engine=self.__engine,
            path=path,
            seen=self._seen,
            errors=self.__errors,
        )

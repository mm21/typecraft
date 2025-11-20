from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Iterable, Self, TypeVar, cast, overload

from ..inspecting.annotations import Annotation
from ..inspecting.generics import extract_arg_map
from .converter import (
    BaseConversionFrame,
    BaseConverter,
    ConverterInterface,
    FuncConverterType,
    FuncConverterWrapper,
)
from .utils import convert_to_dict, convert_to_list, convert_to_set, convert_to_tuple


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
        assert frame.target_annotation.check_instance(converted_obj)

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

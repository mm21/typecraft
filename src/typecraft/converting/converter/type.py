"""
Interface for type-based converters.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Any, cast

from ...inspecting.annotations import Annotation
from ...inspecting.generics import extract_arg
from .base import BaseConversionFrame

if TYPE_CHECKING:
    pass

__all__ = [
    "MatchSpec",
    "BaseTypeConverter",
    "BaseTypeConverterRegistry",
]


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


class TypeConverterInterface[SourceT, TargetT, FrameT: BaseConversionFrame](ABC):
    """
    Defines the interface for type-based converters and mixins.
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
        src_suffix = (
            "[!assignable-from]" if not self.match_spec.assignable_from_source else ""
        )
        tgt_suffix = (
            "[assignable-from]" if self.match_spec.assignable_from_target else ""
        )
        tgt_suffix += (
            "[!assignable-to]" if not self.match_spec.assignable_to_target else ""
        )
        return "{}{} -> {}{}".format(
            self._source_annotation.name,
            src_suffix,
            self._target_annotation.name,
            tgt_suffix,
        )

    def can_convert(
        self,
        obj: SourceT,
        source_annotation: Annotation,
        target_annotation: Annotation,
        /,
    ) -> bool:
        """
        Can be overridden by custom subclasses. Check if converter can convert the given
        object.

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


class BaseTypeConverter[SourceT, TargetT, FrameT: BaseConversionFrame](
    TypeConverterInterface[SourceT, TargetT, FrameT], ABC
):
    """
    Base class for type converters (validators and serializers).

    Encapsulates common conversion parameters and logic for type-based conversion
    between source and target annotations.
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

        return not match_any_union

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


class BaseTypeConverterRegistry[ConverterT: BaseTypeConverter](ABC):
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
        Find the first converter that can handle the conversion, traversing converters
        in reverse order from the order in which they were registered.
        """
        assert not target_annotation.is_union
        for converter in reversed(self._converters):
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
            type(self), BaseTypeConverterRegistry, "ConverterT", BaseTypeConverter
        )
        return cast(type[ConverterT], converter_cls)

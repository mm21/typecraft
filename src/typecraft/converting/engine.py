from __future__ import annotations

import itertools
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, Self, cast

from ..exceptions import BaseConversionError
from ..inspecting.annotations import ANY, Annotation
from ..inspecting.generics import extract_arg
from ..types import (
    COLLECTION_TYPES,
    ValueCollectionType,
)
from ._types import (
    ERROR_SENTINEL,
    ErrorSentinel,
)
from .converter import BaseConversionFrame, BaseConverter, BaseConverterRegistry
from .utils import (
    convert_to_dict,
    convert_to_list,
    convert_to_set,
    convert_to_tuple,
    select_ann_from_union,
)


class BaseConversionEngine[
    RegistryT: BaseConverterRegistry,
    FrameT: BaseConversionFrame,
    ExceptionT: BaseConversionError,
](ABC):
    """
    Base class for conversion engines.

    Orchestrates conversion process, containing common recursion logic with abstract
    hooks for validation/serialization-specific behavior.
    """

    _is_validating: bool
    """
    Whether this engine is for validating.
    """

    __registry_cls: type[RegistryT]
    """
    Registry class with which this conversion engine is parameterized.
    """

    __exception_cls: type[ExceptionT]
    """
    Exception class with which this conversion engine is parameterized.
    """

    __user_registry: RegistryT
    """
    User-registered converters.
    """

    def __init__(self, *, registry: RegistryT | None = None):
        from ..validating import ValidationEngine

        self._is_validating = isinstance(self, ValidationEngine)
        self.__user_registry = registry or self.__registry_cls()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(registry={self.__user_registry})"

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.__registry_cls = cast(
            type[RegistryT],
            extract_arg(cls, BaseConversionEngine, "RegistryT", BaseConverterRegistry),
        )
        cls.__exception_cls = cast(
            type[ExceptionT],
            extract_arg(cls, BaseConversionEngine, "ExceptionT", BaseConversionError),
        )

    @property
    def registry(self) -> RegistryT:
        return self.__user_registry

    def invoke_process(self, obj: Any, frame: FrameT) -> Any:
        """
        Entry point for conversion which handles error aggregation.
        """
        result = self.process(obj, frame)

        # check if any errors were collected during conversion
        if frame.errors:
            raise self.__exception_cls(frame.errors)

        return result

    def process(self, obj: Any, frame: FrameT) -> Any | ErrorSentinel:
        """
        Main conversion dispatcher with common logic.

        Walks the object recursively based on reference annotation, invoking type-based
        converters when conversion is needed.
        """

        # ensure object is an instance of source annotation
        # - would only fail if the user updated the validated data with invalid data,
        # or passed invalid data to serialize() along with an annotation
        if not frame.source_annotation.check_instance(obj, recurse=False):
            frame.append_error(
                obj,
                ValueError(
                    f'Object "{obj}" is not an instance of {frame.source_annotation}'
                ),
            )
            return ERROR_SENTINEL

        # if source is a union, select which specific annotation matches the object
        if frame.source_annotation.is_union:
            frame_ = frame._copy(
                source_annotation=select_ann_from_union(obj, frame.source_annotation)
            )
        else:
            frame_ = frame

        # debug asserts:
        # - can't validate/serialize FROM any: need to know the object type
        # - can't serialize TO any: must have a known supported target type
        # - can validate TO any: check_instance() will just return True
        assert frame_.source_annotation.raw != ANY
        if self._is_serializing:
            assert frame_.target_annotation != ANY

        # invoke conversion if needed
        if not frame_.target_annotation.check_instance(obj, recurse=False):
            return self.__invoke_conversion(obj, frame_)

        # if target is a union, select which specific annotation matches the object
        if frame_.target_annotation.is_union:
            frame_ = frame_._copy(
                target_annotation=select_ann_from_union(obj, frame_.target_annotation)
            )

        # process collections by recursing into them
        if issubclass(frame_.target_annotation.concrete_type, COLLECTION_TYPES):
            return self.__process_collection(obj, frame_)

        # no conversion needed, return as-is
        return obj

    @abstractmethod
    def _get_builtin_registries(self, frame: FrameT) -> tuple[RegistryT, ...]:
        """
        Get builtin registries to use for conversion based on the parameters.
        """

    @classmethod
    def _setup[ConverterT](
        cls,
        *,
        converters: tuple[ConverterT, ...],
        registry: RegistryT | None,
    ) -> Self:
        """
        Setup engine from user-provided args.
        """
        if converters and registry:
            registry_ = cls.__registry_cls(*registry._converters, *converters)
        else:
            registry_ = registry or cls.__registry_cls(*converters)
        return cls(registry=registry_)

    @property
    def _is_serializing(self) -> bool:
        """
        Whether this engine is for serializing.
        """
        return not self._is_validating

    def __process_collection(self, obj: Any, frame: FrameT) -> Any | ErrorSentinel:
        """
        Process collection by recursing into items.

        We can only create built-in collection types; the user is responsible for
        recursing into custom subclasses thereof in a custom converter as the custom
        subclass may have a special construction interface.
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

    def __invoke_conversion(self, obj: Any, frame: FrameT) -> Any | ErrorSentinel:
        if frame.target_annotation.is_union:
            # handle union
            converted_obj = self.__invoke_union_conversion(obj, frame)
        else:
            # handle single target type
            converted_obj = self.__invoke_type_conversion(obj, frame)

        if isinstance(converted_obj, ErrorSentinel):
            return converted_obj

        # ensure conversion succeeded: converter should either raise exception during
        # conversion or return valid data
        possible_types = (
            tuple(a.concrete_type for a in frame.target_annotation.arg_annotations)
            if frame.target_annotation.is_union
            else (frame.target_annotation.concrete_type,)
        )
        if not any(isinstance(converted_obj, t) for t in possible_types):
            frame.append_error(
                obj,
                ValueError(
                    f"{self} failed: got {converted_obj} ({type(converted_obj)})"
                ),
            )
            return ERROR_SENTINEL

        # more thoroughly check type, can be expensive (possibly remove later)
        if not frame.target_annotation.check_instance(converted_obj):
            frame.append_error(
                obj,
                ValueError(
                    f"{self} failed: got {converted_obj} ({type(converted_obj)})"
                ),
            )
            return ERROR_SENTINEL

        return converted_obj

    def __invoke_union_conversion(self, obj: Any, frame: FrameT) -> Any | ErrorSentinel:
        """
        Invoke conversion to union target type.
        """
        assert frame.target_annotation.is_union
        exceptions: list[tuple[Annotation, Exception]] = []

        # attempt each member of union
        assert len(frame.target_annotation.arg_annotations)
        for target_option in frame.target_annotation.arg_annotations:
            converted_obj, exception = self.__attempt_conversion(
                obj, frame, target_option
            )
            if converted_obj is not ERROR_SENTINEL:
                assert not exception
                return converted_obj

            assert exception
            exceptions.append((target_option, exception))

        # no union member converted
        error = "Errors during union member conversion:\n{}".format(
            "\n".join((f"  {t.raw}: {e}" for t, e in exceptions))
        )
        exception = ValueError(error)
        frame.append_error(obj, exception)
        return ERROR_SENTINEL

    def __invoke_type_conversion(self, obj: Any, frame: FrameT) -> Any | ErrorSentinel:
        """
        Invoke conversion to a single (non-union) type.
        """
        assert not frame.target_annotation.is_union
        converted_obj, exception = self.__attempt_conversion(
            obj, frame, frame.target_annotation
        )

        if converted_obj is not ERROR_SENTINEL:
            assert not exception
            return converted_obj

        assert exception
        frame.append_error(obj, exception)
        return ERROR_SENTINEL

    def __attempt_conversion(
        self, obj: Any, frame: FrameT, target_annotation: Annotation
    ) -> tuple[Any | ErrorSentinel, Exception | None]:
        if converter := self.__find_converter(obj, frame, target_annotation):
            frame_ = frame._copy(target_annotation=target_annotation)
            try:
                return (converter.convert(obj, frame_), None)
            except Exception as e:
                if isinstance(e, AssertionError):
                    # indicates an internal framework/converter error; fail immediately
                    raise e from None
                error = ValueError(f"{converter} failed: {e}")
                return (ERROR_SENTINEL, error)
        return (ERROR_SENTINEL, TypeError("No matching converters"))

    def __find_converter(
        self, obj: Any, frame: FrameT, target_annotation: Annotation
    ) -> BaseConverter | None:
        for registry in itertools.chain(
            (self.__user_registry,), self._get_builtin_registries(frame)
        ):
            if converter := registry.find(
                obj, frame.source_annotation, target_annotation
            ):
                return converter
        return None

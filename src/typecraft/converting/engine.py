from __future__ import annotations

import itertools
from abc import ABC, abstractmethod
from collections.abc import Mapping
from functools import cached_property
from typing import Any, Self, cast

from ..inspecting.annotations import ANY, Annotation
from ..inspecting.generics import extract_arg
from ..typedefs import (
    COLLECTION_TYPES,
    ValueCollectionType,
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
](ABC):
    """
    Base class for conversion engines. Orchestrates conversion process, containing
    common recursion logic with abstract hooks for validation/serialization-specific
    behavior.
    """

    __registry_cls: type[RegistryT]
    """
    Registry class which with this conversion engine is parameterized.
    """

    __user_registry: RegistryT
    """
    User-registered converters.
    """

    def __init__(self, *, registry: RegistryT | None = None):
        self.__user_registry = registry or self.__registry_cls()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(registry={self.__user_registry})"

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.__registry_cls = cast(
            type[RegistryT],
            extract_arg(cls, BaseConversionEngine, "RegistryT", BaseConverterRegistry),
        )

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
                source_annotation=select_ann_from_union(obj, frame.source_annotation)
            )
        else:
            frame_ = frame

        # debug asserts:
        # - can't validate/serialize FROM any: need to know the object type
        # - can't serialize TO any: must have a known supported target type
        # - can validate TO any: check_instance() will just return True
        assert frame_.source_annotation != ANY
        if self.__is_serializing:
            assert frame_.target_annotation != ANY

        # invoke conversion if needed
        if not frame_.target_annotation.check_instance(obj, recurse=False):
            return self._invoke_conversion(obj, frame_)

        # if target is a union, select which specific annotation matches the object
        if frame_.target_annotation.is_union:
            frame_ = frame_.copy(
                target_annotation=select_ann_from_union(obj, frame_.target_annotation)
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
        for registry in itertools.chain(
            (self.__user_registry,), self._get_builtin_registries(frame)
        ):
            if converter := registry.find(
                obj, frame.source_annotation, target_annotation
            ):
                return converter
        return None

    @cached_property
    def __is_serializing(self) -> bool:
        """
        Whether the engine is serializing; for debugging only.
        """
        from ..serializing import SerializationEngine

        return isinstance(self, SerializationEngine)

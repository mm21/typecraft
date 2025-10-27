"""
Low-level conversion capability, agnostic of validation vs serialization.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from functools import cached_property
from typing import Any, Self, cast

from .inspecting.annotations import Annotation
from .inspecting.classes import extract_type_param
from .inspecting.functions import ParameterInfo, SignatureInfo
from .typedefs import VarianceType

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

    def invoke(self, obj: SourceT, handle: HandleT) -> TargetT:
        if self.handle_param:
            # invoke with info
            func = cast(Callable[[SourceT, HandleT], TargetT], self.func)
            return func(obj, handle)
        else:
            # invoke without info
            func = cast(Callable[[SourceT], TargetT], self.func)
            return func(obj)


class BaseTypedConverter[SourceT, TargetT, HandleT](ABC):
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

    _func: ConverterFunctionWrapper[SourceT, TargetT, HandleT] | None
    """
    Function taking source type and returning an instance of target type.
    """

    _variance: VarianceType
    """
    Variance with respect to a reference annotation, either source or target depending
    on serialization vs validation.
    """

    def __init__(
        self,
        source_annotation: Any,
        target_annotation: Any,
        /,
        *,
        func: ConverterFuncType[SourceT, TargetT, HandleT] | None = None,
        variance: VarianceType = "contravariant",
    ):
        self._source_annotation = Annotation._normalize(source_annotation)
        self._target_annotation = Annotation._normalize(target_annotation)
        self._func = ConverterFunctionWrapper(func) if func else None
        self._variance = variance

    @property
    def source_annotation(self) -> Annotation:
        return self._source_annotation

    @property
    def target_annotation(self) -> Annotation:
        return self._target_annotation

    @property
    def variance(self) -> VarianceType:
        return self._variance

    @abstractmethod
    def can_convert(self, obj: Any, annotation: Annotation, /) -> bool:
        """
        Check if this converter can convert the given object with the given annotation.

        The meaning of 'annotation' depends on the converter type:
        - For validators: target annotation (converting TO)
        - For serializers: source annotation (converting FROM)
        """

    @classmethod
    def from_func(
        cls,
        func: ConverterFuncType[SourceT, TargetT, HandleT],
        /,
        *,
        variance: VarianceType = "contravariant",
    ) -> Self:
        """
        Create a TypedValidator from a function by inspecting its signature.
        """
        func_wrapper = ConverterFunctionWrapper[Any, TargetT, HandleT](func)

        # validate sig: input and return types must be annotated
        assert func_wrapper.obj_param.annotation
        assert func_wrapper.sig_info.return_annotation

        return cls(
            func_wrapper.obj_param.annotation,
            func_wrapper.sig_info.return_annotation,
            func=func,
            variance=variance,
        )

    def _check_variance_match(
        self,
        annotation: Annotation,
        reference_annotation: Annotation,
    ) -> bool:
        """Check if annotation matches reference based on variance."""
        if self._variance == "invariant":
            # exact match only
            return annotation == reference_annotation
        else:
            # contravariant (default): annotation must be a subclass of reference
            return annotation.is_subtype(reference_annotation)


# TODO: take BaseConverter, can be user-defined subclass (not based on type)
class BaseConverterRegistry[ConverterT: BaseTypedConverter](ABC):
    """
    Base class for converter registries.

    Provides efficient lookup of converters based on object type and annotation.
    Converters are indexed by a key type for fast lookup, with fallback to
    sequential search for contravariant matching.
    """

    _converters: list[ConverterT]
    """
    List of all converters for fallback/contravariant matching.
    """

    def __init__(self, *converters: ConverterT):
        self._converters = []
        self.extend(converters)

    def __len__(self) -> int:
        return len(self._converters)

    def find(self, obj: Any, annotation: Annotation) -> ConverterT | None:
        """
        Find the first converter that can handle the conversion.
        """
        for converter in self._converters:
            if converter.can_convert(obj, annotation):
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
            type(self), BaseConverterRegistry, "ConverterT", BaseTypedConverter
        )
        return cast(type[ConverterT], converter_cls)


class BaseConversionEngine[RegistryT: BaseConverterRegistry](ABC):
    """
    Base class for conversion contexts.

    Encapsulates conversion parameters and provides access to the converter
    registry, propagated throughout the conversion process.
    """

    __registry: RegistryT

    def __init__(self, *, registry: RegistryT | None = None):
        self.__registry = registry or self.__registry_cls()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(registry={self.__registry})"

    @property
    def registry(self) -> RegistryT:
        return self.__registry

    @property
    def __registry_cls(self) -> type[RegistryT]:
        registry_cls = extract_type_param(
            type(self), BaseConversionEngine, "RegistryT", BaseConverterRegistry
        )
        assert registry_cls
        return cast(type[RegistryT], registry_cls)


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

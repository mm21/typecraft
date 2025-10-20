"""
Low-level conversion capability, agnostic of validation vs serialization.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable, Sequence
from typing import Any, cast

from .inspecting.annotations import Annotation
from .inspecting.functions import ParameterInfo, SignatureInfo
from .typedefs import VarianceType


class ConverterFunction:
    """
    Encapsulates a validator or serializer function.
    """

    func: Callable[..., Any]
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

    annotation_param: ParameterInfo | None
    """
    Parameter for annotation, must be keyword.
    """

    context_param: ParameterInfo | None
    """
    Parameter for context, must be keyword.
    """

    def __init__(
        self, func: Callable[..., Any], context_cls: type[BaseConversionContext]
    ):
        sig_info = SignatureInfo(func)

        # get object parameter
        obj_param = next(
            (p for p in sig_info.get_params(positional=True)),
            None,
        )
        assert (
            obj_param
        ), f"Function {func} does not take any positional params, must take obj as positional"

        # get annotation parameter
        annotation_param = next(
            (p for p in sig_info.get_params(annotation=Annotation, keyword=True)),
            None,
        )

        # get context parameter
        context_param = next(
            (p for p in sig_info.get_params(annotation=context_cls, keyword=True)),
            None,
        )

        expected_param_count = sum(
            int(p is not None) for p in (obj_param, annotation_param, context_param)
        )
        if expected_param_count != len(sig_info.params):
            raise TypeError(
                f"Unexpected param count: expected {expected_param_count}, got {len(sig_info.params)}"
            )

        self.func = func
        self.sig_info = sig_info
        self.obj_param = obj_param
        self.annotation_param = annotation_param
        self.context_param = context_param

    def invoke(
        self, obj: Any, annotation: Annotation, context: BaseConversionContext
    ) -> Any:
        kwargs: dict[str, Any] = {}

        if param := self.annotation_param:
            kwargs[param.parameter.name] = annotation
        if param := self.context_param:
            kwargs[param.parameter.name] = context

        return self.func(obj, **kwargs)


class BaseTypedConverter[ConverterFuncT: Callable[..., Any]](ABC):
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

    _func: ConverterFunction | None
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
        func: ConverterFuncT | None = None,
        variance: VarianceType = "contravariant",
    ):
        self._source_annotation = Annotation._normalize(source_annotation)
        self._target_annotation = Annotation._normalize(target_annotation)
        self._func = ConverterFunction(func, self._get_context_cls()) if func else None
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

    @abstractmethod
    def _get_context_cls(self) -> type[BaseConversionContext]:
        """
        Get the context class for this converter.
        """

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


class BaseConverterRegistry[ConverterT: BaseTypedConverter](ABC):
    """
    Base class for converter registries.

    Provides efficient lookup of converters based on object type and annotation.
    Converters are indexed by a key type for fast lookup, with fallback to
    sequential search for contravariant matching.
    """

    _converter_map: dict[type, list[ConverterT]]
    """
    Converters grouped by key type for efficiency.
    """

    _converters: list[ConverterT]
    """
    List of all converters for fallback/contravariant matching.
    """

    def __init__(self, *converters: ConverterT):
        self._converter_map = defaultdict(list)
        self._converters = []
        self.extend(converters)

    def __len__(self) -> int:
        return len(self._converters)

    @property
    def converters(self) -> list[ConverterT]:
        """
        Get converters currently registered.
        """
        return self._converters

    def find(self, obj: Any, annotation: Annotation) -> ConverterT | None:
        """
        Find the first converter that can handle the conversion.

        Searches in order:
        1. Exact key type matches
        2. All converters (for contravariant matching)
        """
        key_type = annotation.concrete_type

        # first try converters registered for the exact key type
        if key_type in self._converter_map:
            for converter in self._converter_map[key_type]:
                if converter.can_convert(obj, annotation):
                    return converter

        # then try all converters (handles contravariant, generic cases)
        for converter in self._converters:
            if converter not in self._converter_map.get(key_type, []):
                if converter.can_convert(obj, annotation):
                    return converter

        return None

    def extend(self, converters: Sequence[ConverterT]):
        """
        Register multiple converters.
        """
        for converter in converters:
            self._register_converter(converter)

    @abstractmethod
    def _get_map_key_type(self, converter: ConverterT) -> type:
        """
        Get the type to use as key in the converter map for this converter.

        - For validators: target type
        - For serializers: source type
        """

    def _register_converter(self, converter: ConverterT):
        """
        Register a converter object.
        """
        map_key = self._get_map_key_type(converter)
        self._converter_map[map_key].append(converter)
        self._converters.append(converter)


class BaseConversionContext[RegistryT: BaseConverterRegistry](ABC):
    """
    Base class for conversion contexts.

    Encapsulates conversion parameters and provides access to the converter
    registry, propagated throughout the conversion process.
    """

    _registry: RegistryT

    def __init__(self, *, registry: RegistryT | None = None):
        self._registry = registry or self._create_default_registry()

    @property
    def registry(self) -> RegistryT:
        return self._registry

    @abstractmethod
    def _create_default_registry(self) -> RegistryT:
        """
        Create a default registry.
        """


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

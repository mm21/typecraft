"""
Low-level conversion capability, agnostic of validation vs serialization.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from .inspecting.annotations import Annotation
from .inspecting.functions import ParameterInfo, SignatureInfo


@dataclass
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

    @classmethod
    def from_func(
        cls, func: Callable[..., Any], context_cls: type[Any]
    ) -> ConverterFunction:
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

        return ConverterFunction(
            func, sig_info, obj_param, annotation_param, context_param
        )

    def invoke(self, obj: Any, annotation: Annotation, context: Any) -> Any:
        kwargs: dict[str, Any] = {}

        if param := self.annotation_param:
            kwargs[param.parameter.name] = annotation
        if param := self.context_param:
            kwargs[param.parameter.name] = context

        return self.func(obj, **kwargs)


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

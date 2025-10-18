"""
Common utilities.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from inspect import Parameter
from typing import Any

from .inspecting import Annotation, FunctionSignatureInfo, ParameterInfo


@dataclass
class ConverterSignature:
    """
    Encapsulates a validator or serializer signature and validates upon creation.
    """

    obj_param: ParameterInfo
    """
    First parameter, the object to be validated/serialized.
    """

    sig_info: FunctionSignatureInfo
    """
    Function signature.
    """

    @classmethod
    def from_func(
        cls, func: Callable[..., Any], context_cls: type[Any]
    ) -> ConverterSignature:
        sig_info = FunctionSignatureInfo(func)

        if not len(sig_info.params) in {1, 3}:
            raise TypeError(
                f"Invalid converter function signature, must take 1 or 3 parameters: {sig_info}"
            )

        # ensure all params are positional
        if not all(
            p.parameter.kind
            in {Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD}
            for p in sig_info.params.values()
        ):
            raise TypeError(
                f"Invalid converter function signature, cannot take keyword-only parameters: {sig_info}"
            )

        # ensure all params match expected types
        if len(sig_info.params) == 1:
            obj_param = next(p for p in sig_info.params.values())
        else:
            obj_param, annotation_param, context_param = sig_info.params.values()
            if not annotation_param.annotation.concrete_type is Annotation:
                raise TypeError(f"Second param must be of type Annotation: {sig_info}")
            if not context_param.annotation.concrete_type is context_cls:
                raise TypeError(
                    f"Third param must be of type {context_cls}: {sig_info}"
                )

        return ConverterSignature(obj_param, sig_info)

"""
Utilities to inspect functions.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from inspect import Parameter
from types import MappingProxyType
from typing import (
    Any,
    get_type_hints,
)

from .annotations import Annotation

__all__ = [
    "ParameterInfo",
    "SignatureInfo",
]


@dataclass
class ParameterInfo:
    """
    Encapsulates information about a function parameter.
    """

    parameter: Parameter
    """
    Parameter from `inspect` module.
    """

    annotation: Annotation | None
    """
    Annotation as extracted by `get_type_hints()`, resolving any stringized annotations.
    """


class SignatureInfo:
    """
    Encapsulates information extracted from a function signature.
    """

    func: Callable[..., Any]
    """
    Function passed in.
    """

    params: MappingProxyType[str, ParameterInfo]
    """
    Mapping of parameter name to info.
    """

    return_annotation: Annotation | None
    """
    Return annotation.
    """

    def __init__(self, func: Callable[..., Any], /):
        self.func = func

        # get type hints to handle stringized annotations from __future__ import
        try:
            type_hints = get_type_hints(func)
        except (NameError, AttributeError) as e:
            raise ValueError(
                f"Failed to resolve type hints for {func.__name__}: {e}. "
                "Ensure all types are imported or defined."
            ) from e

        # set return annotation
        self.return_annotation = (
            Annotation(type_hints["return"]) if "return" in type_hints else None
        )

        # set param annotations
        sig = inspect.signature(func)
        self.params = MappingProxyType(
            {
                name: ParameterInfo(
                    param, Annotation(type_hints[name]) if name in type_hints else None
                )
                for name, param in sig.parameters.items()
            }
        )

    def __repr__(self) -> str:
        return f"{self.func.__name__}({self.params}) -> {self.return_annotation}"

    def get_params_by_annotation(
        self, annotation: Annotation, /
    ) -> MappingProxyType[str, ParameterInfo]:
        """
        Get params with the given annotation, or a subtype thereof.
        """
        return MappingProxyType(
            {
                name: param
                for name, param in self.params.items()
                if param.annotation and param.annotation.is_subtype(annotation)
            }
        )

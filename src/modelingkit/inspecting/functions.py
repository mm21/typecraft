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

    annotation: Annotation
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

    return_annotation: Annotation
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
        if "return" not in type_hints:
            raise ValueError(f"Function {func} has no return type annotation")
        self.return_annotation = Annotation(type_hints["return"])

        # get signature of function
        sig = inspect.signature(func)

        # check for parameters with missing type hints
        missing_type_hints = [p for p in sig.parameters if p not in type_hints]
        if len(missing_type_hints):
            raise ValueError(
                f"Parameters of {func} have no type annotation: {missing_type_hints}"
            )

        # set param annotations
        self.params = MappingProxyType(
            {
                name: ParameterInfo(param, Annotation(type_hints[name]))
                for name, param in sig.parameters.items()
            }
        )

    def __repr__(self) -> str:
        return f"{self.func.__name__}({self.params}) -> {self.return_annotation}"

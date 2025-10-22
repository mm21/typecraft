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
    Generator,
    get_type_hints,
    overload,
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

    @overload
    def get_params(
        self,
        *,
        annotation: Annotation | Any | None = None,
        positional: bool = False,
        keyword: bool = False,
    ) -> Generator[ParameterInfo, None, None]: ...

    @overload
    def get_params(
        self,
        *,
        annotation: Annotation | Any | None = None,
        positional_only: bool = False,
        positional_or_keyword: bool = False,
        keyword_only: bool = False,
        var_positional: bool = False,
        var_keyword: bool = False,
    ) -> Generator[ParameterInfo, None, None]: ...

    def get_params(
        self,
        *,
        annotation: Annotation | Any | None = None,
        positional: bool = False,
        keyword: bool = False,
        positional_only: bool = False,
        positional_or_keyword: bool = False,
        keyword_only: bool = False,
        var_positional: bool = False,
        var_keyword: bool = False,
    ) -> Generator[ParameterInfo, None, None]:
        """
        Get params filtered by annotation (or subtype thereof) and kind.
        """
        kinds: set[int] = set()
        ann = Annotation._normalize(annotation) if annotation else None

        # setup kind filter
        if positional:
            kinds |= {Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD}
        if keyword:
            kinds |= {Parameter.KEYWORD_ONLY, Parameter.POSITIONAL_OR_KEYWORD}
        if positional_only:
            kinds.add(Parameter.POSITIONAL_ONLY)
        if positional_or_keyword:
            kinds.add(Parameter.POSITIONAL_OR_KEYWORD)
        if keyword_only:
            kinds.add(Parameter.KEYWORD_ONLY)
        if var_positional:
            kinds.add(Parameter.VAR_POSITIONAL)
        if var_keyword:
            kinds.add(Parameter.VAR_KEYWORD)

        def check_annotation(param_ann: Annotation | None) -> bool:
            if not ann:
                # no annotation filter specified
                return True
            if not param_ann:
                # annotation filter specified, but this parameter is not annotated
                return False
            return param_ann.is_subtype(ann)

        return (
            p
            for p in self.params.values()
            if p.parameter.kind in kinds and check_annotation(p.annotation)
        )

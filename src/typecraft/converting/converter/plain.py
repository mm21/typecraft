"""
Interface for plain converters, agnostic of source/target type and invoked before or
after type-based conversion.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from ...types import ModeType
from .base import BaseConversionFrame, FuncConverterWrapper

__all__ = [
    "PlainFuncType",
    "PredicateFuncType",
    "BasePlainConverter",
    "BasePlainTransformer",
]

type PlainFuncType[T, FrameT: BaseConversionFrame] = (
    Callable[[T], T] | Callable[[T, FrameT], T]
)
"""
Transformer function: returns the (possibly new) object. Raise to signal failure.

Can optionally take the conversion frame as a second argument.
"""

type PredicateFuncType[T, FrameT: BaseConversionFrame] = (
    Callable[[T], bool] | Callable[[T, FrameT], bool]
)
"""
Predicate function: returns True to pass, False to fail with `PredicateError`.

Runs after type-based conversion, so `T` is the validated target type. Can
optionally take the conversion frame as a second argument.
"""


class BasePlainConverter[FrameT: BaseConversionFrame](ABC):
    """
    Base for plain converters, which run regardless of source/target type before or
    after type-based conversion at their annotation level.
    """

    _func_wrapper: FuncConverterWrapper[Any, Any, FrameT]
    mode: ModeType

    def __init__(self, func: Callable[..., Any], /, *, mode: ModeType = "after"):
        self._func_wrapper = FuncConverterWrapper(func)
        self.mode = mode

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._func_wrapper.func.__name__})"

    @abstractmethod
    def invoke(self, obj: Any, frame: FrameT) -> Any:
        """
        Invoke the wrapped function and return the resulting object.
        """


class BasePlainTransformer[FrameT: BaseConversionFrame](BasePlainConverter[FrameT]):
    """
    Plain transformer: return value replaces the object; exceptions propagate to the
    engine as conversion errors.
    """

    def __init__(
        self,
        func: PlainFuncType[Any, FrameT],
        /,
        *,
        mode: ModeType = "after",
    ):
        super().__init__(func, mode=mode)

    def invoke(self, obj: Any, frame: FrameT) -> Any:
        return self._func_wrapper.invoke(obj, frame)

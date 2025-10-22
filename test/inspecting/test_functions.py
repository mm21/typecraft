"""
Tests for function signature utilities.
"""

from inspect import Parameter
from typing import Any, Optional

import pytest

from typecraft.inspecting.annotations import Annotation
from typecraft.inspecting.functions import ParameterInfo, SignatureInfo


def test_basic_function():
    """
    Test extracting signature from a basic function.
    """

    def func(x: int, y: str) -> bool:
        return True

    sig = SignatureInfo(func)

    assert sig.func is func
    assert isinstance(sig.return_annotation, Annotation)
    assert sig.return_annotation == Annotation(bool)
    assert len(sig.params) == 2

    # check first parameter
    assert "x" in sig.params
    param_x = sig.params["x"]
    assert isinstance(param_x, ParameterInfo)
    assert param_x.annotation == Annotation(int)
    assert param_x.parameter.name == "x"

    # check second parameter
    assert "y" in sig.params
    param_y = sig.params["y"]
    assert param_y.annotation == Annotation(str)
    assert param_y.parameter.name == "y"


def test_no_parameters():
    """
    Test function with no parameters.
    """

    def func() -> int:
        return 42

    sig = SignatureInfo(func)

    assert sig.return_annotation == Annotation(int)
    assert len(sig.params) == 0


def test_missing_annotations():
    """
    Test function with missing parameter and return annotations.
    """

    def func(x):
        return x

    sig = SignatureInfo(func)
    assert len(sig.params) == 1
    assert sig.params["x"].annotation is None
    assert sig.return_annotation is None


def test_stringized_annotations():
    """
    Test that stringized annotations are resolved.
    """

    def func(x: "int", y: "str") -> "bool":
        return True

    sig = SignatureInfo(func)

    assert sig.params["x"].annotation == Annotation(int)
    assert sig.params["y"].annotation == Annotation(str)
    assert sig.return_annotation == Annotation(bool)


def test_forward_reference_error():
    """
    Test that unresolvable forward references raise ValueError.
    """

    def func(x: "NonexistentType") -> int:  # type: ignore
        return 1

    with pytest.raises(ValueError, match="Failed to resolve type hints"):
        SignatureInfo(func)


def test_lambda():
    """
    Test extracting signature from lambda.
    """

    sig = SignatureInfo(lambda x: x + 1)

    assert sig.return_annotation is None
    assert sig.params["x"].annotation is None


def test_variadic_args():
    """
    Test function with *args and **kwargs.
    """

    def func(x: int, *args: str, **kwargs: Any) -> bool:
        return True

    sig = SignatureInfo(func)

    assert len(sig.params) == 3
    assert sig.params["x"].annotation == Annotation(int)
    assert sig.params["args"].annotation == Annotation(str)
    assert sig.params["kwargs"].annotation == Annotation(Any)


def test_parameter_inspection():
    """
    Verify parameter inspection.
    """

    # positional-only
    def func1(x: int, y: str, /) -> bool:
        return True

    sig = SignatureInfo(func1)

    assert len(sig.params) == 2
    assert sig.params["x"].parameter.kind == Parameter.POSITIONAL_ONLY
    assert sig.params["y"].parameter.kind == Parameter.POSITIONAL_ONLY

    def func2(x: int, *, y: str, z: bool) -> None:
        pass

    # keyword-only
    sig = SignatureInfo(func2)

    assert len(sig.params) == 3
    assert sig.params["x"].parameter.kind == Parameter.POSITIONAL_OR_KEYWORD
    assert sig.params["y"].parameter.kind == Parameter.KEYWORD_ONLY
    assert sig.params["z"].parameter.kind == Parameter.KEYWORD_ONLY

    # default values
    def func3(x: int, y: str = "default", z: Optional[bool] = None) -> int:
        return x

    sig = SignatureInfo(func3)

    assert len(sig.params) == 3
    assert sig.params["x"].parameter.default == Parameter.empty
    assert sig.params["y"].parameter.default == "default"
    assert sig.params["z"].parameter.default is None


def test_bound_method():
    """
    Test extracting signature from a bound method.
    """

    class MyClass:
        def method(self, x: int, y: str) -> bool:
            return True

    obj = MyClass()
    sig = SignatureInfo(obj.method)

    # bound method should not include 'self'
    assert len(sig.params) == 2
    assert sig.params["x"].annotation == Annotation(int)
    assert sig.params["y"].annotation == Annotation(str)
    assert "self" not in sig.params


def test_class_method():
    """
    Test extracting signature from a classmethod.
    """

    class MyClass:
        @classmethod
        def method(cls, x: int, y: str) -> bool:
            return True

    sig = SignatureInfo(MyClass.method)

    # classmethod should not include 'cls'
    assert len(sig.params) == 2
    assert sig.params["x"].annotation == Annotation(int)
    assert sig.params["y"].annotation == Annotation(str)
    assert "cls" not in sig.params


def test_static_method():
    """
    Test extracting signature from a static method.
    """

    class MyClass:
        @staticmethod
        def method(x: int, y: str) -> bool:
            return True

    sig = SignatureInfo(MyClass.method)

    assert len(sig.params) == 2
    assert sig.params["x"].annotation == Annotation(int)
    assert sig.params["y"].annotation == Annotation(str)

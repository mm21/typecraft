"""
Tests for function signature utilities.
"""

from inspect import Parameter
from typing import Any, Optional

import pytest

from modelingkit.inspecting.annotations import Annotation
from modelingkit.inspecting.functions import ParameterInfo, SignatureInfo


def test_basic_function():
    """
    Test extracting signature from a basic function.
    """

    def func(x: int, y: str) -> bool:
        return True

    sig_info = SignatureInfo(func)

    assert sig_info.func is func
    assert isinstance(sig_info.return_annotation, Annotation)
    assert sig_info.return_annotation == Annotation(bool)
    assert len(sig_info.params) == 2

    # check first parameter
    assert "x" in sig_info.params
    param_x = sig_info.params["x"]
    assert isinstance(param_x, ParameterInfo)
    assert param_x.annotation == Annotation(int)
    assert param_x.parameter.name == "x"

    # check second parameter
    assert "y" in sig_info.params
    param_y = sig_info.params["y"]
    assert param_y.annotation == Annotation(str)
    assert param_y.parameter.name == "y"


def test_no_parameters():
    """
    Test function with no parameters.
    """

    def func() -> int:
        return 42

    sig_info = SignatureInfo(func)

    assert sig_info.return_annotation == Annotation(int)
    assert len(sig_info.params) == 0


def test_missing_return_annotation():
    """
    Test that missing return annotation raises ValueError.
    """

    def func(x: int):
        return x

    with pytest.raises(ValueError, match="has no return type annotation"):
        SignatureInfo(func)


def test_missing_parameter_annotation():
    """
    Test that missing parameter annotation raises ValueError.
    """

    def func(x: int, y) -> bool:
        return True

    with pytest.raises(ValueError, match="have no type annotation"):
        SignatureInfo(func)


def test_stringized_annotations():
    """
    Test that stringized annotations are resolved.
    """

    def func(x: "int", y: "str") -> "bool":
        return True

    sig_info = SignatureInfo(func)

    assert sig_info.params["x"].annotation == Annotation(int)
    assert sig_info.params["y"].annotation == Annotation(str)
    assert sig_info.return_annotation == Annotation(bool)


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
    func = lambda x: x + 1

    # lambda without annotations should fail
    with pytest.raises(ValueError, match="has no return type annotation"):
        SignatureInfo(func)


def test_variadic_args():
    """
    Test function with *args and **kwargs.
    """

    def func(x: int, *args: str, **kwargs: Any) -> bool:
        return True

    sig_info = SignatureInfo(func)

    assert len(sig_info.params) == 3
    assert sig_info.params["x"].annotation == Annotation(int)
    assert sig_info.params["args"].annotation == Annotation(str)
    assert sig_info.params["kwargs"].annotation == Annotation(Any)


def test_parameter_inspection():
    """
    Verify parameter inspection.
    """

    # positional-only
    def func1(x: int, y: str, /) -> bool:
        return True

    sig_info = SignatureInfo(func1)

    assert len(sig_info.params) == 2
    assert sig_info.params["x"].parameter.kind == Parameter.POSITIONAL_ONLY
    assert sig_info.params["y"].parameter.kind == Parameter.POSITIONAL_ONLY

    def func2(x: int, *, y: str, z: bool) -> None:
        pass

    # keyword-only
    sig_info = SignatureInfo(func2)

    assert len(sig_info.params) == 3
    assert sig_info.params["x"].parameter.kind == Parameter.POSITIONAL_OR_KEYWORD
    assert sig_info.params["y"].parameter.kind == Parameter.KEYWORD_ONLY
    assert sig_info.params["z"].parameter.kind == Parameter.KEYWORD_ONLY

    # default values
    def func3(x: int, y: str = "default", z: Optional[bool] = None) -> int:
        return x

    sig_info = SignatureInfo(func3)

    assert len(sig_info.params) == 3
    assert sig_info.params["x"].parameter.default == Parameter.empty
    assert sig_info.params["y"].parameter.default == "default"
    assert sig_info.params["z"].parameter.default is None


def test_bound_method():
    """
    Test extracting signature from a bound method.
    """

    class MyClass:
        def method(self, x: int, y: str) -> bool:
            return True

    obj = MyClass()
    sig_info = SignatureInfo(obj.method)

    # bound method should not include 'self'
    assert len(sig_info.params) == 2
    assert sig_info.params["x"].annotation == Annotation(int)
    assert sig_info.params["y"].annotation == Annotation(str)
    assert "self" not in sig_info.params


def test_class_method():
    """
    Test extracting signature from a classmethod.
    """

    class MyClass:
        @classmethod
        def method(cls, x: int, y: str) -> bool:
            return True

    sig_info = SignatureInfo(MyClass.method)

    # classmethod should not include 'cls'
    assert len(sig_info.params) == 2
    assert sig_info.params["x"].annotation == Annotation(int)
    assert sig_info.params["y"].annotation == Annotation(str)
    assert "cls" not in sig_info.params


def test_static_method():
    """
    Test extracting signature from a static method.
    """

    class MyClass:
        @staticmethod
        def method(x: int, y: str) -> bool:
            return True

    sig_info = SignatureInfo(MyClass.method)

    assert len(sig_info.params) == 2
    assert sig_info.params["x"].annotation == Annotation(int)
    assert sig_info.params["y"].annotation == Annotation(str)

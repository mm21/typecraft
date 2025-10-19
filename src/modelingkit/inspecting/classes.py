"""
Utilities to inspect classes.
"""

from __future__ import annotations

from typing import (
    Any,
    TypeVar,
    cast,
    get_args,
    get_origin,
    overload,
)

__all__ = [
    "extract_type_param",
]


@overload
def extract_type_param(cls: type[Any], base_cls: type[Any], /) -> type | None: ...


@overload
def extract_type_param[ParamT](
    cls: type[Any], base_cls: type[Any], param_base_cls: type[ParamT], /
) -> type[ParamT] | None: ...


# TODO: pass index of desired param to differentiate multiple type params of the
# same type
def extract_type_param[ParamT](
    cls: type[Any], base_cls: type[Any], param_base_cls: type[ParamT] | None = None, /
) -> type | type[ParamT] | None:
    """
    Extract the concrete type param of `cls` as passed to `base_cls`. If `base_cls` can
    be parameterized with multiple types, it's recommend to also pass `param_base_cls`
    to get the desired type param.
    """

    def check_origin(origin: Any) -> bool:
        return (
            origin is not None
            and isinstance(origin, type)
            and issubclass(origin, base_cls)
        )

    def check_arg(arg: Any) -> bool:
        if arg is None or not isinstance(arg, type):
            return False
        elif param_base_cls and not issubclass(arg, param_base_cls):
            return False
        else:
            return True

    def get_bases(cls: type, attr: str) -> list[type]:
        return list(cast(tuple[type], getattr(cls, attr, ())))

    def get_arg(cls: type) -> type[ParamT] | type | None:
        # check pydantic metadata if applicable
        if metadata := getattr(cls, "__pydantic_generic_metadata__", None):
            origin, args = metadata["origin"], metadata["args"]
        else:
            origin, args = get_origin(cls), get_args(cls)

        if check_origin(origin):
            for arg in args:
                # TODO: check TypeVar bound, but prioritize concrete type?
                if isinstance(arg, TypeVar):
                    continue

                if check_arg(arg):
                    return arg

        # not found, recurse into bases
        for base in get_bases(cls, "__orig_bases__") + get_bases(cls, "__bases__"):
            if param := get_arg(base):
                return param

        return None

    return get_arg(cls)

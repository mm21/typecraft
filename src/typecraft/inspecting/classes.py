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

    def check_arg(arg: Any) -> bool:
        if param_base_cls:
            if not isinstance(arg, type) or not issubclass(arg, param_base_cls):
                return False
        return True

    def get_bases(cls: type, attr: str) -> list[type]:
        return list(cast(tuple[type], getattr(cls, attr, ())))

    def get_arg(
        cls: type, type_var_map: dict[TypeVar, Any]
    ) -> type[ParamT] | type | None:
        # check pydantic metadata if applicable
        if metadata := getattr(cls, "__pydantic_generic_metadata__", None):
            origin, args = metadata["origin"], metadata["args"]
        else:
            origin, args = get_origin(cls), get_args(cls)

        # build type_var_map for this level first
        if origin and isinstance(origin, type):
            # get type parameters of the origin class
            type_params = getattr(origin, "__parameters__", ())

            if type_params and args:
                # create mapping from type parameters to their concrete values
                new_type_var_map = type_var_map.copy()

                for type_param, arg in zip(type_params, args):
                    if isinstance(type_param, TypeVar):
                        if isinstance(arg, TypeVar):
                            # chain TypeVar substitutions
                            if arg in type_var_map:
                                new_type_var_map[type_param] = type_var_map[arg]
                        else:
                            new_type_var_map[type_param] = arg

                type_var_map = new_type_var_map

        if origin is base_cls:
            for arg in args:
                # resolve TypeVar to concrete type if we have a substitution
                if isinstance(arg, TypeVar):
                    if arg in type_var_map:
                        arg = type_var_map[arg]
                    else:
                        # TODO: check TypeVar bound, but prioritize concrete type?
                        continue

                if check_arg(arg):
                    return arg

        # recurse into bases - use origin's bases if we have a generic alias
        base_check = origin if isinstance(origin, type) else cls
        bases = get_bases(base_check, "__orig_bases__") + get_bases(
            base_check, "__bases__"
        )

        for base in bases:
            if param := get_arg(base, type_var_map):
                return param

        return None

    return get_arg(cls, {})

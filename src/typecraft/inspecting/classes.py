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
def extract_type_param(
    cls: type[Any], base_cls: type[Any], name: str, /
) -> type | None: ...


@overload
def extract_type_param[ParamT](
    cls: type[Any], base_cls: type[Any], name: str, param_base_cls: type[ParamT], /
) -> type[ParamT] | None: ...


def extract_type_param[ParamT](
    cls: type[Any],
    base_cls: type[Any],
    name: str,
    param_base_cls: type[ParamT] | None = None,
    /,
) -> type | type[ParamT] | None:
    """
    Extract from `cls` the type parameter that was passed to `base_cls` for its
    parameter named `name`, optionally checking it's a subclass of `param_base_cls`.
    """

    def check_arg(arg: Any) -> bool:
        # validate against param_base_cls if given
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
            # get type parameters of base_cls to find the one with matching name
            base_type_params = getattr(base_cls, "__parameters__", ())

            assert len(base_type_params) == len(
                args
            ), f"Type parameters of {origin} mismatched with args: parameters={base_type_params}, args={args}"

            for type_param, arg in zip(base_type_params, args):
                if isinstance(type_param, TypeVar) and type_param.__name__ == name:
                    # resolve TypeVar to concrete type if we have a substitution
                    if isinstance(arg, TypeVar):
                        if arg in type_var_map:
                            arg = type_var_map[arg]
                        else:
                            continue

                    if not check_arg(arg):
                        raise TypeError(
                            f"Type parameter {name} is {arg}, which does not match "
                            f"required base class {param_base_cls}"
                        )

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

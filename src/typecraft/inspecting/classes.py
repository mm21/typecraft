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
    "extract_args",
    "extract_arg",
]


def extract_args(
    cls: type,
    base_cls: type,
    /,
) -> dict[str, type | TypeVar]:
    """
    Extract from `cls` the type parameters that were passed to `base_cls`.

    :param cls: The class to extract type parameters from
    :param base_cls: The base class whose type parameters should be extracted
    :raises ValueError: If `base_cls` is not in `cls`'s inheritance hierarchy
    :return: Dict mapping parameter names to their resolved types or unresolved TypeVars
    """
    result = _find_args(cls, base_cls, {})
    if result is None:
        raise ValueError(
            f"Base class {base_cls} not found in {cls}'s inheritance hierarchy"
        )
    return result


@overload
def extract_arg(cls: type, base_cls: type, name: str, /) -> type: ...


@overload
def extract_arg(cls: type, base_cls: type, index: int, /) -> type: ...


@overload
def extract_arg[ParamT](
    cls: type, base_cls: type, name: str, param_cls: type[ParamT], /
) -> type[ParamT]: ...


@overload
def extract_arg[ParamT](
    cls: type, base_cls: type, index: int, param_cls: type[ParamT], /
) -> type[ParamT]: ...


def extract_arg[ParamT](
    cls: type,
    base_cls: type,
    name_or_index: str | int,
    param_cls: type[ParamT] | None = None,
    /,
) -> type | type[ParamT]:
    """
    Extract from `cls` the resolved type parameter that was passed to `base_cls`
    for its parameter by name or index, optionally ensuring it's a subclass of
    `param_cls`.
    
    :param cls: The class to extract the type parameter from
    :param base_cls: The base class whose type parameter should be extracted
    :param name_or_index: Parameter name (str) or index (int) to extract
    :param param_cls: Optional base class that the extracted type must be a subclass of
    :raises ValueError: If `base_cls` not found or type parameter is unresolved \
    (TypeVar)
    :raises KeyError: If parameter name not found
    :raises IndexError: If parameter index out of range
    :raises TypeError: If type doesn't match `param_cls` (when provided)
    :return: The resolved type, optionally constrained to `param_cls`
    """

    args = extract_args(cls, base_cls)

    # lookup arg by name or index
    if isinstance(name_or_index, str):
        name = name_or_index
        if name not in args:
            raise KeyError(
                f"Type parameter '{name}' not found in {base_cls}. "
                f"Available parameters: {list(args.keys())}"
            )
        arg = args[name]
        desc = f"name '{name}'"
    else:
        index = name_or_index
        values = list(args.values())
        if index >= len(values):
            raise IndexError(
                f"Type parameter index {index} out of range. "
                f"{base_cls} has {len(values)} parameter(s): {list(args.keys())}"
            )
        arg = values[index]
        desc = f"index {index}"

    if isinstance(arg, TypeVar):
        raise ValueError(f"Type parameter with {desc} is unresolved (TypeVar {arg})")

    if param_cls and not (isinstance(arg, type) and issubclass(arg, param_cls)):
        raise TypeError(
            f"Type parameter with {desc} is {arg}, which does not match "
            f"required base class {param_cls}"
        )

    return arg


def _get_bases(cls: type, attr: str) -> list[type]:
    return list(cast(tuple[type], getattr(cls, attr, ())))


def _find_args(
    cls: type, base_cls: type, type_var_map: dict[TypeVar, Any]
) -> dict[str, type | TypeVar] | None:

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
        base_type_params = cast(tuple[Any], getattr(base_cls, "__parameters__", ()))

        assert len(base_type_params) == len(
            args
        ), f"Type parameters of {origin} mismatched with args: parameters={base_type_params}, args={args}"

        arg_map: dict[str, type | TypeVar] = {}

        for type_param, arg in zip(base_type_params, args):
            assert isinstance(type_param, TypeVar)

            # resolve TypeVar to concrete type if we have a substitution
            if isinstance(arg, TypeVar) and arg in type_var_map:
                arg = type_var_map[arg]

            # arg could technically be a list[int] (GenericAlias),
            # int | str (UnionType), etc - not a concrete type, but a type which
            # type checkers will understand
            arg_map[type_param.__name__] = arg

        return arg_map

    # recurse into bases - use origin's bases if we have a generic alias
    base_check = origin if isinstance(origin, type) else cls
    bases = _get_bases(base_check, "__orig_bases__") + _get_bases(
        base_check, "__bases__"
    )

    for base in bases:
        if args := _find_args(base, base_cls, type_var_map):
            return args

    return None

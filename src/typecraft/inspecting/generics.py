"""
Utilities to inspect classes.
"""

from __future__ import annotations

from typing import (
    Any,
    Literal,
    TypeVar,
    cast,
    get_args,
    get_origin,
    overload,
)

from ._utils import safe_issubclass

__all__ = [
    "extract_args",
    "extract_arg_map",
    "extract_arg",
    "normalize_args",
]


def extract_args(cls: type, base_cls: type) -> tuple[type | TypeVar, ...]:
    """
    Extract from `cls` the type parameters that were passed to `base_cls`.

    :param cls: The class to extract type parameters from
    :param base_cls: The base class whose type parameters should be extracted
    :raises TypeError: If `base_cls` is not in `cls`'s inheritance hierarchy
    :return: Dict mapping parameter names to their resolved types or unresolved TypeVars
    """
    args = _find_args(cls, base_cls)
    if args is None:
        raise TypeError(
            f"Base class {base_cls} not found in {cls}'s inheritance hierarchy"
        )

    args_list: list[type | TypeVar] = []
    for arg in args:
        if isinstance(arg, tuple):
            _, type_ = arg
            args_list.append(type_)
        else:
            args_list.append(arg)

    return tuple(args_list)


def extract_arg_map(
    cls: type,
    base_cls: type,
    /,
) -> dict[str, type | TypeVar]:
    """
    Extract from `cls` a mapping of type parameter names to parameters that were
    passed to `base_cls`.

    :param cls: The class to extract type parameters from
    :param base_cls: The base class whose type parameters should be extracted
    :raises TypeError: If `base_cls` is not in `cls`'s inheritance hierarchy
    :return: Dict mapping parameter names to their resolved types or unresolved TypeVars
    """
    args = _find_args(cls, base_cls)
    if args is None:
        raise TypeError(
            f"Base class {base_cls} not found in {cls}'s inheritance hierarchy"
        )

    arg_map: dict[str, type | TypeVar] = {}
    for arg in args:
        if isinstance(arg, tuple):
            name, type_ = arg
            arg_map[name] = type_

    return arg_map


@overload
def extract_arg(cls: type, base_cls: type, name: str, /) -> type: ...


@overload
def extract_arg(cls: type, base_cls: type, index: int, /) -> type: ...


@overload
def extract_arg[ParamT](
    cls: type, base_cls: type, name: str, arg_cls: type[ParamT], /
) -> type[ParamT]: ...


@overload
def extract_arg[ParamT](
    cls: type, base_cls: type, index: int, arg_cls: type[ParamT], /
) -> type[ParamT]: ...


def extract_arg[ParamT](
    cls: type,
    base_cls: type,
    name_or_index: str | int,
    arg_cls: type[ParamT] | None = None,
    /,
) -> type | type[ParamT]:
    """
    Extract from `cls` the resolved type parameter that was passed to `base_cls`
    for its parameter by name or index, optionally ensuring it's a subclass of
    `param_cls`.

    :param cls: The class or annotation to extract the type parameter from
    :param base_cls: The base class whose type parameter should be extracted
    :param name_or_index: Parameter name (str) or index (int) to extract
    :param param_cls: Optional base class that the extracted type must be a subclass of
    :raises TypeError: If `base_cls` is not in `cls`'s inheritance hierarchy
    :raises ValueError: If type parameter is found, but unresolved (is a TypeVar)
    :raises KeyError: If parameter name not found
    :raises IndexError: If parameter index out of range
    :raises TypeError: If type doesn't match `param_cls` (when provided)
    :return: The resolved type, optionally constrained to `param_cls`
    """

    if isinstance(name_or_index, str):
        # lookup by name
        args = extract_arg_map(cls, base_cls)
        name = name_or_index
        if name not in args:
            raise KeyError(
                f"Type parameter '{name}' not found in {base_cls}. "
                f"Available parameters: {list(args.keys())}"
            )
        arg = args[name]
        desc = f"name '{name}'"
    else:
        args = extract_args(cls, base_cls)
        index = name_or_index
        if index >= len(args):
            raise IndexError(
                f"Type parameter index {index} out of range. "
                f"{base_cls} has {len(args)} parameter(s): {args}"
            )
        arg = args[index]
        desc = f"index {index}"

    if isinstance(arg, TypeVar):
        raise ValueError(
            f"Type parameter with {desc} is unresolved (TypeVar {arg}): cls={cls}, base_cls={base_cls}"
        )

    if arg_cls and not (isinstance(arg, type) and issubclass(arg, arg_cls)):
        raise TypeError(
            f"Type parameter with {desc} is {arg}, which does not match "
            f"required base class {arg_cls}"
        )

    return arg


def normalize_args(args: tuple[type | TypeVar, ...]) -> tuple[type, ...]:
    """
    Normalize args to types, replacing TypeVars with Any.
    """
    return tuple(cast(type, Any) if isinstance(a, TypeVar) else a for a in args)


def _find_args(
    cls: type, base_cls: type, type_var_map: dict[TypeVar, Any] | None = None
) -> list[type | tuple[str, type | TypeVar]] | None:
    tv_map = type_var_map if type_var_map is not None else {}

    # check pydantic metadata if applicable
    if metadata := getattr(cls, "__pydantic_generic_metadata__", None):
        origin, args = metadata["origin"], cast(tuple[Any, ...], metadata["args"])
    else:
        origin, args = get_origin(cls), get_args(cls)

    # handle the case where cls is directly base_cls (not a generic alias)
    # but only if it's not a parameterized version of something else
    if cls is base_cls and origin is None:
        # return unresolved TypeVars with their names
        base_type_params = _get_parameters(base_cls, type_vars=True)
        return [(t.__name__, t) for t in base_type_params]

    # check if base_cls is an ABC/protocol not literally in the hierarchy
    # but still compatible via issubclass
    check_origin = origin if isinstance(origin, type) else cls
    needs_abc_fallback = False

    # handle typing generic aliases like typing.Sequence by getting their origin
    base_cls_origin = get_origin(base_cls) or base_cls

    if isinstance(check_origin, type) and isinstance(base_cls_origin, type):
        # check if base_cls is in the MRO - if not, we might need ABC fallback
        if base_cls_origin not in check_origin.__mro__ and safe_issubclass(
            check_origin, base_cls_origin
        ):
            needs_abc_fallback = True

    # build type_var_map for this level first
    if origin and isinstance(origin, type):
        type_params = _get_parameters(origin)
        tv_map = _update_typevar_map(tv_map, type_params, args)

    if origin is base_cls or (needs_abc_fallback and origin is base_cls_origin):
        base_type_params = _get_parameters(base_cls, type_vars=True)
        return _build_args_list(base_type_params, args, tv_map)

    # recurse into bases - use origin's bases if we have a generic alias
    base_check = origin if isinstance(origin, type) else cls
    bases = _get_bases(base_check, "__orig_bases__") + _get_bases(
        base_check, "__bases__"
    )

    for base in bases:
        if (result := _find_args(base, base_cls, tv_map)) is not None:
            return result

    # if we need ABC fallback and didn't find base_cls in the hierarchy,
    # the args from cls should correspond to the type parameters of base_cls
    if needs_abc_fallback and args:
        base_type_params = _get_parameters(base_cls_origin, type_vars=True)
        return _build_args_list(base_type_params, args, tv_map)

    return None


@overload
def _get_parameters(cls: type) -> tuple[Any, ...]: ...


@overload
def _get_parameters(cls: type, *, type_vars: Literal[True]) -> tuple[TypeVar, ...]: ...


def _get_parameters(cls: type, *, type_vars: bool = False) -> tuple[Any, ...]:
    """
    Get `__parameters__` attribute, defaulting to an empty tuple.
    """
    parameters = cast(tuple[Any, ...], getattr(cls, "__parameters__", ()))
    if type_vars:
        for p in parameters:
            assert isinstance(p, TypeVar), f"Not a TypeVar: {p}"
    return parameters


def _get_bases(cls: type, attr: str) -> list[type]:
    return list(cast(tuple[type], getattr(cls, attr, ())))


def _resolve_typevar(arg: Any, tv_map: dict[TypeVar, Any]) -> Any:
    """
    Resolve a TypeVar through the substitution map.
    """
    return tv_map.get(arg, arg) if isinstance(arg, TypeVar) else arg


def _build_args_list(
    type_params: tuple[TypeVar, ...],
    args: tuple[Any, ...],
    tv_map: dict[TypeVar, Any],
) -> list[type | tuple[str, type | TypeVar]]:
    """
    Build an args list from type parameters and arguments, resolving TypeVars.

    :param type_params: Type parameters from the base class
    :param args: Concrete type arguments
    :param tv_map: TypeVar substitution map
    :return: List of resolved types or (name, type) tuples
    """
    args_list: list[type | tuple[str, type | TypeVar]] = []

    if type_params:
        # has named type parameters
        assert len(type_params) == len(
            args
        ), f"Type parameters mismatched with args: parameters={type_params}, args={args}"

        for type_param, arg in zip(type_params, args):
            resolved = _resolve_typevar(arg, tv_map)
            args_list.append((type_param.__name__, resolved))
    else:
        # builtin-style: no named parameters, just positional args
        for arg in args:
            resolved = _resolve_typevar(arg, tv_map)
            if isinstance(arg, TypeVar):
                args_list.append((arg.__name__, resolved))
            else:
                args_list.append(cast(type, resolved))

    return args_list


def _update_typevar_map(
    tv_map: dict[TypeVar, Any],
    type_params: tuple[Any, ...],
    args: tuple[Any, ...],
) -> dict[TypeVar, Any]:
    """
    Update TypeVar substitution map with new mappings from type params to args.

    :param tv_map: Existing TypeVar substitution map
    :param type_params: Type parameters to map from
    :param args: Concrete type arguments to map to
    :return: Updated TypeVar map
    """
    if not type_params or not args:
        return tv_map

    new_tv_map = tv_map.copy()

    for type_param, arg in zip(type_params, args):
        if isinstance(type_param, TypeVar):
            if isinstance(arg, TypeVar):
                # chain TypeVar substitutions
                if arg in tv_map:
                    new_tv_map[type_param] = tv_map[arg]
            else:
                new_tv_map[type_param] = arg

    return new_tv_map

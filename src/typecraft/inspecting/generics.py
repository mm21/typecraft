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
    "extract_arg_map",
    "extract_arg",
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
    
    :param cls: The class or annotation to extract the type parameter from
    :param base_cls: The base class whose type parameter should be extracted
    :param name_or_index: Parameter name (str) or index (int) to extract
    :param param_cls: Optional base class that the extracted type must be a subclass of
    :raises TypeError: If `base_cls` is not in `cls`'s inheritance hierarchy
    :raises ValueError: If `base_cls` not found or type parameter is unresolved \
    (TypeVar)
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

    if param_cls and not (isinstance(arg, type) and issubclass(arg, param_cls)):
        raise TypeError(
            f"Type parameter with {desc} is {arg}, which does not match "
            f"required base class {param_cls}"
        )

    return arg


def _get_bases(cls: type, attr: str) -> list[type]:
    return list(cast(tuple[type], getattr(cls, attr, ())))


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
        base_type_params = cast(tuple[Any], getattr(base_cls, "__parameters__", ()))
        # return unresolved TypeVars with their names
        return [(t.__name__, t) for t in base_type_params]

    # check if base_cls is an ABC/protocol not literally in the hierarchy
    # but still compatible via issubclass
    check_origin = origin if isinstance(origin, type) else cls
    needs_abc_fallback = False

    # handle typing generic aliases like typing.Sequence by getting their origin
    base_cls_origin = get_origin(base_cls) or base_cls

    if isinstance(check_origin, type) and isinstance(base_cls_origin, type):
        try:
            # check if base_cls is in the MRO - if not, we might need ABC fallback
            if base_cls_origin not in check_origin.__mro__ and issubclass(
                check_origin, base_cls_origin
            ):
                needs_abc_fallback = True
        except TypeError:
            # issubclass can raise TypeError for some types
            pass

    # build type_var_map for this level first
    if origin and isinstance(origin, type):
        # get type parameters of the origin class
        type_params = getattr(origin, "__parameters__", ())

        if type_params and args:
            # create mapping from type parameters to their concrete values
            new_tv_map = tv_map.copy()

            for type_param, arg in zip(type_params, args):
                if isinstance(type_param, TypeVar):
                    if isinstance(arg, TypeVar):
                        # chain TypeVar substitutions
                        if arg in tv_map:
                            new_tv_map[type_param] = tv_map[arg]
                    else:
                        new_tv_map[type_param] = arg

            tv_map = new_tv_map

    if origin is base_cls or (needs_abc_fallback and origin is base_cls_origin):
        # get type parameters of base_cls to find the one with matching name
        base_type_params = cast(tuple[Any], getattr(base_cls, "__parameters__", ()))

        args_list: list[type | tuple[str, type | TypeVar]] = []

        if not len(base_type_params):
            # builtin, e.g. list[int] or tuple[int, str]
            # still need to resolve TypeVars if present
            for arg in args:
                a = tv_map.get(arg, arg) if isinstance(arg, TypeVar) else arg
                if isinstance(arg, TypeVar):
                    args_list.append((arg.__name__, a))
                else:
                    args_list.append(cast(type, a))
        else:
            # should have typevars and args
            assert len(base_type_params) == len(
                args
            ), f"Type parameters of {origin} mismatched with args: parameters={base_type_params}, args={args}"

            for type_param, arg in zip(base_type_params, args):
                assert isinstance(type_param, TypeVar)

                # resolve TypeVar to concrete type if we have a substitution
                if isinstance(arg, TypeVar) and arg in tv_map:
                    arg = tv_map[arg]

                # arg could technically be a list[int] (GenericAlias),
                # int | str (UnionType), etc - not a concrete type, but a type which
                # type checkers will understand
                args_list.append((type_param.__name__, arg))

        return args_list

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
        # for ABCs like Sequence, we need to get type parameters from base_cls_origin

        # if base_cls is a generic alias like Sequence[int], get its args
        base_type_params = cast(
            tuple[Any], getattr(base_cls_origin, "__parameters__", ())
        )

        # if base_cls has no __parameters__ (common for typing ABCs), we need to
        # figure out the parameter names - for builtins we just use positional
        if base_type_params:
            # has named type parameters
            args_list: list[type | tuple[str, type | TypeVar]] = []
            for type_param, arg in zip(base_type_params, args):
                assert isinstance(type_param, TypeVar)

                # resolve TypeVar to concrete type if we have a substitution
                if isinstance(arg, TypeVar) and arg in tv_map:
                    arg = tv_map[arg]

                args_list.append((type_param.__name__, arg))

            return args_list
        else:
            # treat as builtin-style: no named parameters, just positional args
            args_list: list[type | tuple[str, type | TypeVar]] = []
            for arg in args:
                a = tv_map.get(arg, arg) if isinstance(arg, TypeVar) else arg
                args_list.append(cast(type, a))
            return args_list

    return None

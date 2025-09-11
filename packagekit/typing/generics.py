from typing import Any, TypeVar, cast, get_args, get_origin, overload


@overload
def get_type_param[BaseT](cls: type, base_cls: type[BaseT]) -> type | None: ...


@overload
def get_type_param[BaseT, ParamT](
    cls: type, base_cls: type[BaseT], param_base_cls: type[ParamT]
) -> type[ParamT] | None: ...


def get_type_param[BaseT, ParamT](
    cls: type, base_cls: type[BaseT], param_base_cls: type[ParamT] | None = None
) -> type[ParamT] | type | None:
    """
    Extract the concrete type param from the given base class. If `base_cls` can be
    parameterized with multiple types, it's recommend to also pass `param_base_cls`
    to get the desired type param.
    """

    def get_bases(cls: type, attr: str) -> list[type]:
        return list(cast(tuple[type], getattr(cls, attr, ())))

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

    def check_cls(cls: type) -> type[ParamT] | type | None:

        # check for pydantic model first
        if pydantic_generic_metadata := getattr(
            cls, "__pydantic_generic_metadata__", None
        ):
            origin = pydantic_generic_metadata["origin"]
            if check_origin(origin):
                for arg in pydantic_generic_metadata["args"]:
                    if check_arg(arg):
                        return arg

        bases = get_bases(cls, "__orig_bases__") + get_bases(cls, "__bases__")
        for base in bases:
            origin = get_origin(base)
            if not check_origin(origin):
                continue

            for arg in get_args(base):

                # TODO: check TypeVar bound, but prioritize concrete type?
                if isinstance(arg, TypeVar):
                    continue

                if check_arg(arg):
                    return arg

        # not found, recurse into each base
        for base in bases:
            if param := check_cls(base):
                return param

        return None

    return check_cls(cls)

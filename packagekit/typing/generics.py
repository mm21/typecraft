from typing import TypeVar, get_args, get_origin


def extract_type_param[BaseT, ParamT](
    cls, base_cls: type[BaseT], param_base_cls: type[ParamT] | None = None
) -> type[ParamT] | None:
    """
    Extract the concrete type param with the given class. If `base_cls` can be
    parameterized with multiple types, it's recommend to also pass `param_base_cls`
    to get the desired type param.
    """

    # check for pydantic model
    if pydantic_generic_metadata := getattr(cls, "__pydantic_generic_metadata__", None):
        origin = pydantic_generic_metadata["origin"]
        if origin is not None and issubclass(origin, base_cls):
            for arg in pydantic_generic_metadata["args"]:
                if isinstance(arg, type):
                    return arg

    orig_bases = getattr(cls, "__orig_bases__", ())

    for base in orig_bases:
        origin = get_origin(base)

        # skip if not desired base class
        if (
            not origin
            or not isinstance(origin, type)
            or not issubclass(origin, base_cls)
        ):
            continue

        for arg in get_args(base):

            # TODO: get TypeVar bound, but prioritize concrete type?
            if isinstance(arg, TypeVar):
                continue

            if not isinstance(arg, type):
                continue

            if param_base_cls and not issubclass(arg, param_base_cls):
                continue

            return arg

    return None

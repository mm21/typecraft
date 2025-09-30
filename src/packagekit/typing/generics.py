from types import UnionType
from typing import Annotated, Any, TypeVar, Union, cast, get_args, get_origin, overload

__all__ = [
    "AnnotationInfo",
    "normalize_annotation",
    "flatten_annotation",
    "extract_type",
    "get_type_param",
]


class AnnotationInfo:
    """
    Performs normalizations on annotation and encapsulates useful info.
    """

    annotation: Any
    """
    Original annotation after stripping `Annotated[]` if applicable.
    """

    extras: tuple[Any, ...]
    """
    Extra annotations, if `Annotated[]` was used.
    """

    annotations: tuple[Any, ...]
    """
    Annotation(s) with unions flattened if applicable.
    """

    types: tuple[type[Any], ...]
    """
    Concrete (non-generic) annotation(s) with unions flattened if applicable.
    """

    def __init__(self, raw_annotation: Any, /):
        # get extras if applicable
        annotation, extras = normalize_annotation(raw_annotation)

        # get constituent annotations from union if applicable
        annotations = flatten_annotation(annotation)

        # get non-parameterized types
        types = tuple(extract_type(normalize_annotation(a)[0]) for a in annotations)

        self.annotation = annotation
        self.extras = extras
        self.annotations = annotations
        self.types = types


def normalize_annotation(annotation: Any, /) -> tuple[Any, tuple[Any, ...]]:
    """
    Split Annotated[x, ...] (if present) into annotation and extras.
    """
    if get_origin(annotation) is Annotated:
        args = get_args(annotation)
        assert len(args)

        annotation_ = args[0]
        extras = tuple(args[1:])
    else:
        annotation_ = annotation
        extras = ()

    return annotation_, extras


def flatten_annotation(annotation: Any, /) -> tuple[Any, ...]:
    """
    Flatten union (if present) into its constituent types.
    """
    annotation_ = normalize_annotation(annotation)[0]
    return (
        get_args(annotation_)
        if type(annotation_) is UnionType or get_origin(annotation_) is Union
        else (annotation_,)
    )


def extract_type(annotation: Any, /) -> type[Any]:
    """
    Get concrete type of parameterized annotation if applicable.
    """
    annotation_ = normalize_annotation(annotation)[0]
    type_ = get_origin(annotation_) or annotation_
    if not isinstance(type_, type):
        raise ValueError(
            f"Could not extract type from annotation '{annotation_}', got '{type_}'"
        )
    return type_


@overload
def get_type_param[BaseT](cls: type[Any], base_cls: type[BaseT]) -> type | None: ...


@overload
def get_type_param[BaseT, ParamT](
    cls: type[Any], base_cls: type[BaseT], param_base_cls: type[ParamT]
) -> type[ParamT] | None: ...


# TODO: pass index of desired param to differentiate multiple type params of the
# same type
def get_type_param[BaseT, ParamT](
    cls: type[Any], base_cls: type[BaseT], param_base_cls: type[ParamT] | None = None
) -> type[ParamT] | type | None:
    """
    Extract the concrete type param from the given base class. If `base_cls` can be
    parameterized with multiple types, it's recommend to also pass `param_base_cls`
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

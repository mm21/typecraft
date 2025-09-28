"""
Utilities to normalize objects.
"""

from dataclasses import dataclass
from typing import Any, Callable, Iterable

__all__ = [
    "Converter",
    "normalize_obj",
    "normalize_objs",
]


@dataclass
class Converter[TargetT]:
    """
    Encapsulates type conversion info mapping one or more types to the target type.
    """

    factory: Callable[[Any], TargetT]
    """
    Callable returning an instance of target type. Must take exactly one positional
    argument of one of the type(s) given in `from_types`. May be the target type itself
    if its constructor takes exactly one positional argument.
    """

    from_types: tuple[Any, ...]
    """
    Types from which to convert using factory.
    """


def normalize_obj[TargetT](
    obj: Any,
    target_type: type[TargetT],
    /,
    *converters: Converter[TargetT],
) -> TargetT:
    """
    Normalize object to the target type, converting if applicable.
    """
    if isinstance(obj, target_type):
        return obj
    else:
        # try to convert using provided specs
        for converter in converters:
            if isinstance(obj, converter.from_types):
                # convert using this spec
                obj_norm = converter.factory(obj)

                if not isinstance(obj_norm, target_type):
                    note = f"and converter {converter} failed (got {obj_norm})"
                    raise ValueError(_err_str(obj, target_type, note))

                return obj_norm

        # could not convert
        if len(converters):
            note = f"and cannot be converted from {converters}"
        else:
            note = None

        raise ValueError(_err_str(obj, target_type, note))


def normalize_objs[TargetT](
    obj_or_objs: Any | Iterable[Any],
    target_type: type[TargetT],
    /,
    *converters: Converter[TargetT],
) -> list[TargetT]:
    """
    Normalize object(s) to a list of the target type, converting if applicable.
    """
    # check if the object can be converted by any converter
    if not isinstance(obj_or_objs, Iterable) or any(
        isinstance(obj_or_objs, c.from_types) for c in converters
    ):
        objs = [obj_or_objs]
    else:
        objs = obj_or_objs

    # normalize each object
    return [normalize_obj(o, target_type, *converters) for o in objs]


def _err_str(obj: Any, target_type: type[Any], note: str | None = None) -> str:
    note_ = f" {note}" if note else ""
    return (
        f"Object {obj} of type {type(obj)} is not of expected type {target_type}{note_}"
    )

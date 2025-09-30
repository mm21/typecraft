"""
Utilities to convert and normalize objects.
"""

from types import GeneratorType
from typing import Any, Callable, Iterable

__all__ = [
    "Converter",
    "Normalizer",
    "normalize_obj",
    "normalize_objs",
]


class Converter[T]:
    """
    Encapsulates type conversion info.
    """

    __factory: Callable[[Any], T]
    """
    Callable returning an instance of target type. Must take exactly one positional
    argument of one of the type(s) given in `from_types`. May be the target type itself
    if its constructor takes exactly one positional argument.
    """

    __source_types: tuple[type[Any], ...]
    """
    Type(s) to convert from. An empty tuple means factory can accept any type.
    """

    def __init__(
        self, factory: Callable[[Any], T], source_types: tuple[type[Any], ...] = ()
    ):
        self.__factory = factory
        self.__source_types = source_types

    def __repr__(self) -> str:
        return (
            f"Converter(factory={self.__factory}, source_types={self.__source_types})"
        )

    @property
    def source_types(self) -> tuple[type[Any], ...]:
        return self.__source_types

    def convert(self, obj: Any, /) -> T:
        """
        Convert object using factory.
        """
        if not self.can_convert(obj):
            raise ValueError(f"Object {obj} ({type(obj)}) cannot be converted")
        return self.__factory(obj)

    def can_convert(self, obj: Any, /) -> bool:
        """
        Check if this converter can convert the given object.
        """
        return len(self.__source_types) == 0 or isinstance(obj, self.__source_types)


class Normalizer[T]:

    __target_type: type[T]
    __converters: tuple[Converter[T], ...]

    def __init__(self, target_type: type[T], *converters: Converter[T]):
        self.__target_type = target_type
        self.__converters = converters

    def normalize_obj(self, obj: Any, /) -> T:
        return normalize_obj(obj, self.__target_type, *self.__converters)

    def normalize_objs(self, obj_or_objs: Any, /) -> list[T]:
        return normalize_objs(obj_or_objs, self.__target_type, *self.__converters)

    def can_normalize(self, obj: Any, target_type: type[Any], /) -> bool:
        return issubclass(self.__target_type, target_type) and any(
            c.can_convert(obj) for c in self.__converters
        )


def normalize_obj[T](
    obj: Any,
    target_type: type[T],
    /,
    *converters: Converter[T],
) -> T:
    """
    Normalize object to the target type, converting if applicable.
    """
    if isinstance(obj, target_type):
        return obj
    else:
        # try to convert using provided specs
        obj_norm: Any = None
        converter: Converter | None = None
        for converter in converters:
            if converter.can_convert(obj):
                obj_norm = converter.convert(obj)
                converter = converter
                break

        if not isinstance(obj_norm, target_type):
            raise ValueError(
                f"Object {obj} ({type(obj)}) could not be converted to {target_type}, converter={converter}"
            )

        return obj_norm


def normalize_objs[T](
    obj_or_objs: Any,
    target_type: type[T],
    /,
    *converters: Converter[T],
) -> list[T]:
    """
    Normalize object(s) to a list of the target type, converting if applicable.

    Only built-in collection types and generators are expanded.
    Custom types (even if iterable) are treated as single objects.
    """
    # normalize to an iterable of objects
    if isinstance(obj_or_objs, (list, tuple, set, frozenset, range, GeneratorType)):
        objs = obj_or_objs
    else:
        objs = [obj_or_objs]

    # normalize each object and place in a new list
    return [normalize_obj(o, target_type, *converters) for o in objs]

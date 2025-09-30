"""
Utilities to convert and normalize objects with recursive type support.
"""

from collections.abc import Mapping, Sequence, Set
from types import GeneratorType
from typing import Any, Callable, Sized, cast, get_args, get_origin

from ..typing.generics import AnnotationInfo

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

    __target_type: type[T]
    """
    Type to convert to.
    """

    __source_types: tuple[type[Any], ...]
    """
    Type(s) to convert from. An empty tuple means factory can accept any type.
    """

    __factory: Callable[[Any], T] | None
    """
    Callable returning an instance of target type. Must take exactly one positional
    argument of one of the type(s) given in `from_types`. May be the target type itself
    if its constructor takes exactly one positional argument.
    """

    def __init__(
        self,
        target_type: type[T],
        source_types: tuple[type[Any], ...] = (),
        factory: Callable[[Any], T] | None = None,
    ):
        self.__target_type = target_type
        self.__source_types = source_types
        self.__factory = factory

    def __repr__(self) -> str:
        return f"Converter(target_type={self.__target_type}, source_types={self.__source_types}, factory={self.__factory})"

    @property
    def target_type(self) -> type[T]:
        return self.__target_type

    @property
    def source_types(self) -> tuple[type[Any], ...]:
        return self.__source_types

    def convert(self, obj: Any, /) -> T:
        """
        Convert object using factory.
        """
        if not self.can_convert(obj, self.__target_type):
            raise ValueError(
                f"Object '{obj}' ({type(obj)}) cannot be converted using {self}"
            )

        factory = self.__factory or cast(Callable[[Any], T], self.__target_type)
        new_obj = factory(obj)
        if not isinstance(new_obj, self.__target_type):
            raise ValueError(
                f"Converter {self} failed to convert {obj} ({type(obj)}), got {new_obj} ({type(new_obj)})"
            )

        return new_obj

    def can_convert(self, obj: Any, target_type: type[Any], /) -> bool:
        """
        Check if this converter can convert the given object.
        """
        target_match = issubclass(target_type, self.__target_type)
        source_match = len(self.__source_types) == 0 or isinstance(
            obj, self.__source_types
        )
        return target_match and source_match


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
            c.can_convert(obj, target_type) for c in self.__converters
        )


def normalize_obj[T](
    obj: Any,
    target_type: type[T],
    /,
    *converters: Converter[T],
) -> T:
    """
    Recursively normalize object to the target type, converting if applicable.

    Handles nested parameterized types like list[list[int]] by recursively
    applying converters at each level.
    """
    info = AnnotationInfo(target_type)

    # handle union types by trying each constituent type
    if len(info.annotations) > 1:
        for annotation in info.annotations:
            try:
                return normalize_obj(obj, annotation, *converters)
            except (ValueError, TypeError):
                continue
        raise ValueError(
            f"Object {obj} could not be converted to any member of {target_type}"
        )

    # at this point we should have exactly 1 annotation and corresponding
    # concrete type
    assert len(info.annotations) == 1
    assert len(info.types) == 1
    annotation = info.annotations[0]
    concrete_type = info.types[0]

    if issubclass(concrete_type, (Sequence, Set, Mapping)) and get_origin(annotation):
        return _normalize_container(obj, annotation, converters)

    # handle non-parameterized types
    if isinstance(obj, concrete_type):
        return obj

    converter = _find_converter(obj, concrete_type, converters)
    if converter:
        return converter.convert(obj)

    # try direct construction if type is callable
    if callable(concrete_type):
        try:
            return cast(T, concrete_type(obj))  # type: ignore
        except (TypeError, ValueError):
            pass

    raise ValueError(
        f"Object '{obj}' ({type(obj)}) could not be converted to {target_type}"
    )


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
    info = AnnotationInfo(target_type)

    can_convert = False
    for type_ in info.types:
        if any(c.can_convert(obj_or_objs, type_) for c in converters):
            can_convert = True
            break

    # normalize to a container of objects
    if not can_convert and isinstance(
        obj_or_objs, (Sequence, Set, range, GeneratorType)
    ):
        objs = obj_or_objs
    else:
        # can convert it, or it's not a container
        objs = [obj_or_objs]

    # normalize each object and place in a new list
    return [normalize_obj(o, target_type, *converters) for o in objs]


def _find_converter(
    obj: Any, target_type: type[Any], converters: tuple[Converter, ...]
) -> Converter | None:
    """
    Find the first converter that can handle the given object to target type conversion.
    """
    for converter in converters:
        if converter.can_convert(obj, target_type):
            return converter
    return None


def _normalize_container(
    obj: Any, annotation: Any, converters: tuple[Converter, ...]
) -> Any:
    """
    Normalize container of objects.
    """
    container_type = get_origin(annotation)
    assert isinstance(container_type, type)
    assert issubclass(container_type, (Sequence, Set, Mapping))

    args = get_args(annotation)
    assert len(args)

    # invoke generator to ensure object is sized
    if isinstance(obj, GeneratorType):
        container = list(obj)
    else:
        assert isinstance(obj, Sized)
        container = obj

    # TODO: convert container first, pass target container to normalizers?

    # TODO: check if object is valid as-is

    if issubclass(container_type, Sequence):
        assert isinstance(container, (Sequence, Set))
        return _normalize_sequence(container, container_type, args, converters)
    elif issubclass(container_type, Set):
        assert isinstance(container, (Sequence, Set))
        return _normalize_set(container, container_type, args, converters)
    else:
        assert isinstance(container, Mapping)
        return _normalize_mapping(container, container_type, args, converters)


def _normalize_sequence(
    container: Sequence[Any] | Set[Any],
    container_type: type[Sequence[Any]],
    args: tuple[Any, ...],
    converters: tuple[Converter, ...],
) -> Any:

    # handle fixed-length tuples like tuple[int, str, float]
    if issubclass(container_type, tuple) and args[-1] != ...:
        if len(container) != len(args):
            raise ValueError(
                f"Tuple length mismatch: expected {len(args)}, got {len(container)}"
            )
        normalized_objs = [
            normalize_obj(o, type_, *converters) for o, type_ in zip(container, args)
        ]
    else:
        # homogeneous containers
        if issubclass(container_type, tuple):
            assert len(args) == 2
        else:
            assert len(args) == 1
        type_ = args[0]
        normalized_objs = [normalize_obj(o, type_, *converters) for o in container]

    converter = _find_converter(normalized_objs, container_type, converters)
    if converter:
        return converter.convert(normalized_objs)
    else:
        return container_type(normalized_objs)  # type: ignore


def _normalize_set(
    container: Sequence[Any] | Set[Any],
    container_type: type[Set[Any]],
    args: tuple[Any, ...],
    converters: tuple[Converter, ...],
) -> Any:
    assert len(args) == 1
    type_ = args[0]
    normalized_objs = {normalize_obj(o, type_, *converters) for o in container}

    converter = _find_converter(normalized_objs, container_type, converters)
    if converter:
        return converter.convert(normalized_objs)
    else:
        return container_type(normalized_objs)  # type: ignore


def _normalize_mapping(
    container: Mapping[Any, Any],
    container_type: type[Mapping[Any, Any]],
    args: tuple[Any, ...],
    converters: tuple[Converter, ...],
) -> Any:
    assert len(args) == 2
    key_type, value_type = args

    normalized_objs = {
        normalize_obj(k, key_type, *converters): normalize_obj(
            v, value_type, *converters
        )
        for k, v in container.items()
    }

    converter = _find_converter(normalized_objs, container_type, converters)
    if converter:
        return converter.convert(normalized_objs)
    else:
        return container_type(**normalized_objs)

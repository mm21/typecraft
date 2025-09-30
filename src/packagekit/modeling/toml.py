"""
Layer to map TOML files (via `tomlkit`) to/from dataclasses.
"""

from __future__ import annotations

import datetime
from abc import ABC, abstractmethod
from datetime import date as Date
from datetime import datetime as DateTime
from datetime import time as Time
from functools import cached_property
from pathlib import Path
from types import NoneType
from typing import (
    Any,
    Iterable,
    MutableMapping,
    MutableSequence,
    Self,
    TypedDict,
    cast,
    get_args,
    get_origin,
    overload,
)

import tomlkit
from tomlkit import TOMLDocument
from tomlkit.items import (
    AbstractTable,
    AoT,
    Array,
    Bool,
    Date,
    DateTime,
    Float,
    InlineTable,
    Integer,
    Item,
    String,
    Table,
    Time,
    Trivia,
)

from ..typing.generics import get_type_param
from .dataclasses import BaseValidatedDataclass, FieldInfo

__all__ = [
    "BaseDocumentWrapper",
    "BaseTableWrapper",
    "BaseInlineTableWrapper",
    "FieldMetadata",
    "ArrayWrapper",
    "TableArrayWrapper",
    "ArrayItemType",
]

type BuiltinType = str | int | float | bool | datetime.date | datetime.time | datetime.datetime
type TomlkitType = String | Integer | Float | Bool | Date | Time | DateTime | Item | Array | AbstractTable

type ValueType = BaseTomlWrapper | TomlkitType
"""
Type after normalization.
"""

type ArrayItemType = BuiltinType | TomlkitType | BaseInlineTableWrapper | ArrayWrapper
"""
Types which can be used as fields of array items.
"""

# keep in sync with BuiltinType
BUILTIN_TYPES = (
    str,
    int,
    float,
    bool,
    datetime.date,
    datetime.time,
    datetime.datetime,
)

# keep in sync with TomlkitType
TOMLKIT_TYPES = (
    String,
    Integer,
    Float,
    Bool,
    Date,
    Time,
    DateTime,
    Item,
    Array,
    AbstractTable,
)

CONTAINER_TYPES = (
    *BUILTIN_TYPES,
    *TOMLKIT_TYPES,
)
"""
Types which can be used as fields of containers (in addition to wrapper types).
"""


class BaseTomlWrapper[TomlkitT](ABC):
    """
    Base wrapper for a class from `tomlkit`, providing additional features like mapping
    to/from dataclasses.
    """

    _tomlkit_obj: TomlkitT | None = None
    """
    Corresponding object from `tomlkit`, either extracted upon load or newly created.
    """

    @property
    def tomlkit_obj(self) -> TomlkitT:
        """
        Get tomlkit object, creating it if it doesn't exist.
        """
        if not self._tomlkit_obj:
            self._set_tomlkit_obj(self._create_tomlkit_obj())
        assert self._tomlkit_obj
        return self._tomlkit_obj

    @classmethod
    @abstractmethod
    def _wrap_tomlkit_obj(
        cls,
        tomlkit_obj: TomlkitT,
        *,
        annotation: Any | None = None,
    ) -> Self:
        """
        Create an instance of this class from the corresponding tomlkit object.
        """
        ...

    @abstractmethod
    def _create_tomlkit_obj(self) -> TomlkitT:
        """
        Create corresponding tomlkit object.
        """
        ...

    @abstractmethod
    def _propagate_tomlkit_obj(self, tomlkit_obj: TomlkitT): ...

    @classmethod
    def _from_tomlkit_obj(
        cls,
        tomlkit_obj: TomlkitT,
        *,
        annotation: Any | None = None,
    ) -> Self:
        """
        Instantiate this wrapper object to wrap a `tomlkit` object.
        """
        tomlkit_cls = cls._get_tomlkit_cls()

        if not isinstance(tomlkit_obj, tomlkit_cls):
            raise ValueError(
                f"Object has invalid type: expected {tomlkit_cls}, got {type(tomlkit_obj)} ({tomlkit_obj})"
            )

        obj = cls._wrap_tomlkit_obj(tomlkit_obj, annotation=annotation)
        obj._set_tomlkit_obj(tomlkit_obj, bypass_propagate=True)
        return obj

    @classmethod
    def _get_tomlkit_cls(cls) -> type[TomlkitT]:
        """
        Get corresponding tomlkit class.
        """
        tomlkit_cls = get_type_param(cls, BaseTomlWrapper)
        assert tomlkit_cls, f"Could not get type param for {cls}"
        return tomlkit_cls

    @cached_property
    def _tomlkit_cls(self) -> type[TomlkitT]:
        return type(self)._get_tomlkit_cls()

    def _set_tomlkit_obj(self, tomlkit_obj: TomlkitT, bypass_propagate: bool = False):
        """
        Set tomlkit object, ensuring it has not already been set.
        """
        assert isinstance(tomlkit_obj, self._tomlkit_cls)
        assert self._tomlkit_obj is None, f"tomlkit_obj has already been set on {self}"
        self._tomlkit_obj = tomlkit_obj

        if not bypass_propagate:
            self._propagate_tomlkit_obj(tomlkit_obj)


class BaseContainerWrapper[TomlkitT: MutableMapping[str, Any]](
    BaseValidatedDataclass, BaseTomlWrapper[TomlkitT]
):
    """
    Base container for items in a document or table. Upon reading a TOML file via
    `tomlkit`, coerces values from `tomlkit` types to the corresponding type
    in this package.

    Only primitives (`str`, `int`, `float`, `bool`, `date`, `time`, `datetime`),
    `tomlkit` item types, and `tomlkit` wrapper types are allowed as fields.
    """

    def __new__(cls, *args, **kwargs) -> Self:
        # validate unions before proceeding with object creation
        for name, field_info in cls.dataclass_fields().items():
            assert len(field_info.annotations) == len(field_info.concrete_annotations)
            if len(field_info.concrete_annotations) > 1:
                if (
                    len(field_info.concrete_annotations) != 2
                    or field_info.concrete_annotations[0] is NoneType
                    or field_info.concrete_annotations[1] is not NoneType
                ):
                    raise TypeError(
                        f"Class {cls}: Field '{name}': Unions must consist of (type) | None, got {field_info.annotation}"
                    )
        return super().__new__(cls, *args, **kwargs)

    def __setattr__(self, name: str, value: Any):
        super().__setattr__(name, value)

        # if applicable, propagate to wrapped tomlkit object
        if self._tomlkit_obj and (
            field_info := type(self).dataclass_fields().get(name)
        ):
            self._propagate_field(self._tomlkit_obj, field_info, getattr(self, name))

    @classmethod
    def dataclass_valid_types(cls) -> tuple[Any, ...]:
        return (
            BaseTableWrapper,
            BaseInlineTableWrapper,
            ArrayWrapper,
            TableArrayWrapper,
            *CONTAINER_TYPES,
            NoneType,
        )

    def dataclass_normalize(self, field_info: FieldInfo, value: Any) -> Any:
        annotation = field_info.annotations[0]
        concrete_annotation = field_info.concrete_annotations[0]

        if value is None:
            return None
        elif issubclass(concrete_annotation, BaseTomlWrapper) and not isinstance(
            value, concrete_annotation
        ):
            return concrete_annotation._from_tomlkit_obj(value, annotation=annotation)
        else:
            return _normalize_value(value)

    @classmethod
    def _wrap_tomlkit_obj(cls, tomlkit_obj: TomlkitT, **_) -> Self:
        """
        Extract model fields from container and return instance of this model with
        the original container stored.
        """
        values: dict[str, Any] = {}

        for name, field_info in cls.dataclass_fields().items():
            field_name = cls._get_field_name(field_info)
            if value := tomlkit_obj.get(field_name):
                values[name] = value

        return cls(**values)

    @classmethod
    def _get_field_name(cls, field_info: FieldInfo) -> str:
        """
        Get name of field, handling alias if applicable.
        """
        return field_info.field.metadata.get("alias", field_info.field.name)

    def _propagate_tomlkit_obj(self, tomlkit_obj: TomlkitT):
        for name, field_info in type(self).dataclass_fields().items():
            value = getattr(self, name, None)
            if value is None:
                continue
            self._propagate_field(tomlkit_obj, field_info, value)

    def _propagate_field(
        self, tomlkit_obj: TomlkitT, field_info: FieldInfo, value: Any
    ):
        """
        Propagate field to this container's tomlkit obj.
        """
        field_name = type(self)._get_field_name(field_info)
        if value is None:
            if field_name in tomlkit_obj:
                del tomlkit_obj[field_name]
        else:
            tomlkit_obj[field_name] = (
                value.tomlkit_obj if isinstance(value, BaseTomlWrapper) else value
            )


class BaseDocumentWrapper(BaseContainerWrapper[TOMLDocument]):
    """
    Abstracts a TOML document.

    Saves the parsed `TOMLDocument` upon loading so it can be
    updated upon storing, preserving item attributes like whether arrays are multiline.
    """

    @classmethod
    def load(cls, file: Path, /) -> Self:
        """
        Load this document from a file.
        """
        assert file.is_file()
        return cls.loads(file.read_text())

    @classmethod
    def loads(cls, string: str, /) -> Self:
        return cls._from_tomlkit_obj(tomlkit.loads(string))

    def dump(self, file: Path, /):
        file.write_text(self.dumps())

    def dumps(self) -> str:
        return tomlkit.dumps(self.tomlkit_obj)

    def _create_tomlkit_obj(self) -> TOMLDocument:
        return TOMLDocument()


class BaseTableWrapper(BaseContainerWrapper[Table]):
    """
    Abstracts a table with nested primitive types or other tables.
    """

    def _create_tomlkit_obj(self) -> Table:
        return tomlkit.table()


class BaseInlineTableWrapper(BaseContainerWrapper[InlineTable]):
    """
    Abstracts an inline table with nested primitive types.
    """

    def _create_tomlkit_obj(self) -> InlineTable:
        return tomlkit.inline_table()


class FieldMetadata(TypedDict):
    """
    Encapsulates metadata for a field definition in a document, table, or inline table.
    """

    alias: str
    """
    Field name to use when accessing the toml document.
    """


class BaseArrayWrapper[TomlkitT: list, ItemT](
    MutableSequence[ItemT], BaseTomlWrapper[TomlkitT]
):
    """
    Base array of either primitive types or tables.
    """

    __list: list[ItemT]
    """
    List of values, whether tomlkit objects or wrappers.
    """

    @overload
    def __init__(self): ...

    @overload
    def __init__(self, iterable: Iterable[ItemT], /): ...

    def __init__(self, iterable: Iterable[ItemT] | None = None):
        self.__list = []
        if iterable:
            self += iterable

    @overload
    def __getitem__(self, index: int) -> ItemT: ...

    @overload
    def __getitem__(self, index: slice) -> list[ItemT]: ...

    def __getitem__(self, index: int | slice) -> ItemT | list[ItemT]:
        return self.__list[index]

    @overload
    def __setitem__(self, index: int, value: ItemT): ...

    @overload
    def __setitem__(self, index: slice, value: Iterable[ItemT]): ...

    def __setitem__(self, index: int | slice, value: ItemT | Iterable[ItemT]):
        if isinstance(index, int):
            value_ = _normalize_value(value)
            self.__list[index] = cast(ItemT, value_)
            if self._tomlkit_obj:
                self._tomlkit_obj[index] = _normalize_item(value_)
        else:
            assert isinstance(index, slice)
            assert isinstance(value, Iterable)
            value_ = _normalize_values(value)
            self.__list[index] = cast(list[ItemT], value_)
            if self._tomlkit_obj:
                self._tomlkit_obj[index] = _normalize_items(value_)

    def __delitem__(self, index: int | slice):
        del self.__list[index]
        if self._tomlkit_obj:
            del self._tomlkit_obj[index]

    def __len__(self) -> int:
        return len(self.__list)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({list(self)})"

    def __eq__(self, other: Any) -> bool:
        return list(self) == other

    def insert(self, index: int, value: ItemT):
        value_ = _normalize_value(value)
        self.__list.insert(index, cast(ItemT, value_))
        if self._tomlkit_obj:
            self._tomlkit_obj.insert(index, _normalize_item(value_))

    @staticmethod
    @abstractmethod
    def _get_item_values(tomlkit_obj: TomlkitT) -> list[Any]:
        """
        Get contained tomlkit objects from this tomlkit object.
        """
        ...

    @classmethod
    def _wrap_tomlkit_obj(
        cls, tomlkit_obj: TomlkitT, *, annotation: Any | None = None
    ) -> Self:
        # get type with which this array is parameterized
        assert annotation, "No annotation"
        item_cls, item_annotation = cls._get_item_cls(annotation)

        # get raw values
        item_values = cls._get_item_values(tomlkit_obj)

        # populate new array with values
        if issubclass(item_cls, BaseTomlWrapper):
            items = [
                item_cls._from_tomlkit_obj(i, annotation=item_annotation)
                for i in item_values
            ]
        else:
            items = item_values

        return cls(items)

    def _propagate_tomlkit_obj(self, tomlkit_obj: TomlkitT):
        assert len(tomlkit_obj) == 0
        tomlkit_obj += _normalize_items(self.__list)

    @classmethod
    def _get_item_cls(cls, annotation: Any) -> tuple[type[ItemT], Any]:
        """
        Get type with which this array is parameterized as (concrete type, full type).
        """
        # get full type with which this array is parameterized,
        # e.g. Array[int] from Array[Array[int]]
        args = get_args(annotation)
        assert (
            len(args) == 1
        ), f"Array must be parameterized with exactly one type, got {args}"

        item_type = args[0]  # e.g. Array[int]
        item_cls = cast(type[ItemT], get_origin(item_type) or item_type)

        return item_cls, item_type


class ArrayWrapper[ItemT: ArrayItemType](BaseArrayWrapper[Array, ItemT]):
    """
    Array of primitive types.
    """

    def _create_tomlkit_obj(self) -> Array:
        return Array([], Trivia())

    @staticmethod
    def _get_item_values(tomlkit_obj: Array) -> list[Any]:
        return tomlkit_obj.value


class TableArrayWrapper[TableT: BaseTableWrapper](BaseArrayWrapper[AoT, TableT]):
    """
    Array of tables.
    """

    def _create_tomlkit_obj(self) -> AoT:
        return AoT([])

    @staticmethod
    def _get_item_values(tomlkit_obj: AoT) -> list[Any]:
        return tomlkit_obj.body


def _normalize_value(value: Any) -> ValueType:
    """
    Normalize value to `BaseTomlWrapper` or tomlkit item.
    """
    if isinstance(value, BaseTomlWrapper):
        return value
    elif isinstance(value, TOMLKIT_TYPES):
        return value
    else:
        return tomlkit.item(value)


def _normalize_values(values: Iterable[Any]) -> list[ValueType]:
    """
    Normalize values to `BaseTomlWrapper`s or items.
    """
    return [_normalize_value(v) for v in values]


def _normalize_item(obj: ValueType) -> TomlkitType:
    """
    Normalize object to tomlkit item.
    """
    if isinstance(obj, BaseTomlWrapper):
        return obj.tomlkit_obj
    else:
        assert isinstance(obj, TOMLKIT_TYPES)
        return obj


def _normalize_items(objs: Iterable[Any]) -> list[Any]:
    """
    Normalize objects to tomlkit items.
    """
    return [_normalize_item(o) for o in objs]

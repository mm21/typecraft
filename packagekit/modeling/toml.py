"""
Layer to map TOML files (via `tomlkit`) to/from Pydantic models.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date as Date
from datetime import datetime as DateTime
from datetime import time as Time
from functools import cached_property
from pathlib import Path
from typing import (
    Any,
    Iterable,
    MutableMapping,
    MutableSequence,
    Self,
    cast,
    get_args,
    get_origin,
    overload,
)

import tomlkit
import tomlkit.items
from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator
from pydantic.fields import FieldInfo
from tomlkit.items import Trivia

from ..typing.generics import get_type_param

type ArrayItemType = str | int | float | bool | Date | Time | DateTime | BaseInlineTable | Array
"""
Types which can be used as fields of array items.
"""

__all__ = [
    "BaseDocument",
    "BaseTable",
    "BaseInlineTable",
    "Array",
    "TableArray",
    "ArrayItemType",
]


class BaseTomlElement[TomlkitT](ABC):
    """
    Abstracts a TOML element corresponding to a type from `tomlkit`.
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
    def _coerce(
        cls,
        tomlkit_obj: TomlkitT,
        annotation: type[Any] | None = None,
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
        annotation: type[Any] | None = None,
    ) -> Self:
        tomlkit_cls = cls._get_tomlkit_cls()
        assert isinstance(
            tomlkit_obj, tomlkit_cls
        ), f"Object has invalid type: expected {tomlkit_cls}, got {type(tomlkit_obj)} ({tomlkit_obj})"

        obj = cls._coerce(tomlkit_obj, annotation)
        obj._set_tomlkit_obj(tomlkit_obj, bypass_propagate=True)
        return obj

    @classmethod
    def _get_tomlkit_cls(cls) -> type[TomlkitT]:
        """
        Get corresponding tomlkit class.
        """
        tomlkit_cls = get_type_param(cls, BaseTomlElement)
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


class BaseContainer[TomlkitT: MutableMapping[str, Any]](
    BaseModel, BaseTomlElement[TomlkitT]
):
    """
    Container for items in a document or table. Upon reading a TOML file via
    `tomlkit`, coerces values from `tomlkit` types to the corresponding class
    in this package.

    Only primitives (`str`, `int`, `float`, `bool`, `date`, `time`, `datetime`)
    and `BaseTomlElement` subclasses are allowed as fields.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    def __setattr__(self, name: str, value: Any):
        """
        Set attribute on model and additionally write through to tomlkit object.
        """
        super().__setattr__(name, value)
        if self._tomlkit_obj and (field_info := type(self).model_fields.get(name)):
            self._propagate_field(self._tomlkit_obj, name, field_info, value)

    @field_validator("*", mode="before", check_fields=False)
    @classmethod
    def validate_field(cls, value: Any, info: ValidationInfo) -> Any:
        assert info.field_name

        field_cls, annotation = cls._get_field_type(info.field_name)

        # coerce value if type is element
        if issubclass(field_cls, BaseTomlElement):
            return field_cls._from_tomlkit_obj(value, annotation=annotation)

        return value

    @classmethod
    def _get_field_type(cls, field_name: str) -> tuple[type[Any], type[Any]]:
        """
        Get the field type as (concrete class, annotation).
        """
        field_info = cls.model_fields.get(field_name)
        assert field_info

        annotation = field_info.annotation
        assert annotation

        return (get_origin(annotation) or annotation, annotation)

    @classmethod
    def _coerce(
        cls, tomlkit_obj: TomlkitT, annotation: type[Any] | None = None
    ) -> Self:
        """
        Extract model fields from container and return instance of this model with
        the original container stored.
        """
        fields: dict[str, Any] = {}

        for name in cls.model_fields.keys():
            if name in tomlkit_obj:
                fields[name] = tomlkit_obj[name]

        return cls(**fields)

    def _propagate_tomlkit_obj(self, tomlkit_obj: TomlkitT):
        # propagate all fields
        for name, field_info in type(self).model_fields.items():
            value = getattr(self, name, None)
            if value is None:
                continue
            self._propagate_field(tomlkit_obj, name, field_info, value)

    def _propagate_field(
        self, tomlkit_obj: TomlkitT, name: str, field_info: FieldInfo, value: Any
    ):
        """
        Propagate field to this container's tomlkit obj.
        """
        field_name = field_info.alias or name
        field_tomlkit_obj = (
            value.tomlkit_obj if isinstance(value, BaseTomlElement) else value
        )

        # TODO: handle None: delete corresponding field?
        tomlkit_obj[field_name] = field_tomlkit_obj

        if not isinstance(value, BaseTomlElement):
            # refresh this model's value as it may have been converted by tomlkit
            object.__setattr__(self, name, tomlkit_obj[field_name])


class BaseDocument(BaseContainer[tomlkit.TOMLDocument]):
    """
    Abstracts a TOML document.

    Saves the parsed `tomlkit.TOMLDocument` upon loading so it can be
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
        # TODO
        ...

    def dumps(self) -> str:
        # TODO
        ...

    def _create_tomlkit_obj(self) -> tomlkit.TOMLDocument:
        return tomlkit.TOMLDocument()


class BaseTable(BaseContainer[tomlkit.items.Table]):
    """
    Abstracts a table with nested primitive types or other tables.
    """

    def _create_tomlkit_obj(self) -> tomlkit.items.Table:
        return tomlkit.table()


class BaseInlineTable(BaseContainer[tomlkit.items.InlineTable]):
    """
    Abstracts an inline table with nested primitive types.
    """

    def _create_tomlkit_obj(self) -> tomlkit.items.InlineTable:
        return tomlkit.inline_table()


class BaseArray[TomlkitT: list, ItemT](
    MutableSequence[ItemT], BaseTomlElement[TomlkitT]
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
            value_ = cast(ItemT, value)
            self.__list[index] = value_
            if self._tomlkit_obj:
                self._tomlkit_obj[index] = self._normalize_item(value_)
                self._refresh_item(index)
        else:
            assert isinstance(index, slice)
            assert isinstance(value, Iterable)
            value_ = list(value)  # in case value is a generator
            self.__list[index] = value_
            if self._tomlkit_obj:
                self._tomlkit_obj[index] = self._normalize_items(value_)
                start, stop, stride = index.indices(len(self.__list))
                for i in range(start, stop, stride):
                    self._refresh_item(i)

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
        self.__list.insert(index, value)
        if self._tomlkit_obj:
            self._tomlkit_obj.insert(index, self._normalize_item(value))
            self._refresh_item(index)

    @staticmethod
    @abstractmethod
    def _get_item_values(tomlkit_obj: TomlkitT) -> list[Any]:
        """
        Get contained tomlkit objects from this tomlkit object.
        """
        ...

    @classmethod
    def _coerce(
        cls, tomlkit_obj: TomlkitT, annotation: type[Any] | None = None
    ) -> Self:
        # get type with which this array is parameterized
        assert annotation, "No annotation"
        item_cls, item_type = cls._get_item_cls(annotation)

        # get raw values
        item_values = cls._get_item_values(tomlkit_obj)

        # populate new array with values
        if issubclass(item_cls, BaseTomlElement):
            items = [
                item_cls._from_tomlkit_obj(i, annotation=item_type) for i in item_values
            ]
        else:
            items = item_values

        return cls(items)

    def _propagate_tomlkit_obj(self, tomlkit_obj: TomlkitT):
        assert len(tomlkit_obj) == 0
        tomlkit_obj += self._normalize_items(self.__list)

        # also refresh own items if applicable
        for i, item in enumerate(self.__list):
            if not isinstance(item, BaseTomlElement):
                self.__list[i] = tomlkit_obj[i]

    @classmethod
    def _get_item_cls(cls, annotation: type[Any]) -> tuple[type[ItemT], type[Any]]:
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

    def _normalize_item(self, item: ItemT) -> Any:
        """
        Normalize input to tomlkit object.
        """
        return item.tomlkit_obj if isinstance(item, BaseTomlElement) else item

    def _normalize_items(self, items: Iterable[ItemT]) -> list[Any]:
        """
        Normalize inputs to tomlkit object.
        """
        return [self._normalize_item(i) for i in items]

    def _refresh_item(self, index: int):
        """
        Refresh item at index if applicable; it may have been converted from a
        primitive to an item by tomlkit.
        """
        assert self.tomlkit_obj
        value = self.__list[index]
        if isinstance(value, BaseTomlElement):
            return
        self.__list[index] = cast(ItemT, self.tomlkit_obj[index])


class Array[ItemT: ArrayItemType](BaseArray[tomlkit.items.Array, ItemT]):
    """
    Array of primitive types.
    """

    def _create_tomlkit_obj(self) -> tomlkit.items.Array:
        return tomlkit.items.Array([], Trivia())

    @staticmethod
    def _get_item_values(tomlkit_obj: tomlkit.items.Array) -> list[Any]:
        return tomlkit_obj.value


class TableArray[TableT: BaseTable](BaseArray[tomlkit.items.AoT, TableT]):
    """
    Array of tables.
    """

    def _create_tomlkit_obj(self) -> tomlkit.items.AoT:
        return tomlkit.items.AoT([])

    @staticmethod
    def _get_item_values(tomlkit_obj: tomlkit.items.AoT) -> list[Any]:
        return tomlkit_obj.body

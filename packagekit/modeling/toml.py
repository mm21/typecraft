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
    Iterator,
    Mapping,
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

    __tomlkit_obj: TomlkitT | None = None
    """
    Corresponding object from `tomlkit`, either extracted upon load or newly created.
    """

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
        obj._tomlkit_obj = tomlkit_obj
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

    @property
    def _tomlkit_obj(self) -> TomlkitT:
        """
        Get tomlkit object, creating it if it doesn't exist.
        """
        if not self.__tomlkit_obj:
            self.__tomlkit_obj = self._create_tomlkit_obj()
        return self.__tomlkit_obj

    @_tomlkit_obj.setter
    def _tomlkit_obj(self, tomlkit_obj: TomlkitT):
        """
        Set tomlkit object, ensuring it has not already been set.
        """
        assert isinstance(tomlkit_obj, self._tomlkit_cls)
        if self.__tomlkit_obj:
            raise AttributeError(f"tomlkit_obj has already been set on {self}")
        self.__tomlkit_obj = tomlkit_obj

    # TODO: method to get tomlkit_obj, creating it if it doesn't exist


# TODO: validate all fields upon class creation
class BaseContainer[TomlkitT: Mapping](BaseModel, BaseTomlElement[TomlkitT]):
    """
    Container for items in a document or table. Upon reading a TOML file via
    `tomlkit`, coerces values from `tomlkit` types to the corresponding class
    in this package.

    Only primitives (`str`, `int`, `float`, `bool`, `date`, `time`, `datetime`)
    and `BaseTomlElement` subclasses are allowed as fields.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

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


class ItemMapping[KT, VT](MutableMapping[KT, VT]):
    """
    Maintains a mapping based on object ids and a list of the objects in order to
    preserve their reference counts. Especially useful for non-hashable objects.
    """

    _id_map: dict[int, VT]
    """
    Mapping of key id to object.
    """

    _key_list: list[KT]
    """
    List of key objects.
    """

    def __init__(self):
        self._id_map = {}
        self._key_list = []

    def __getitem__(self, key: KT) -> VT:
        key_id = id(key)
        if key_id not in self._id_map:
            raise KeyError(key)
        return self._id_map[key_id]

    def __setitem__(self, key: KT, value: VT) -> None:
        key_id = id(key)

        # if key doesn't exist, add it to item list to preserve reference
        if key_id not in self._id_map:
            self._key_list.append(key)

        self._id_map[key_id] = value

    def __delitem__(self, key: KT) -> None:
        key_id = id(key)

        if key_id not in self._id_map:
            raise KeyError(key)

        # remove from id mapping
        del self._id_map[key_id]

        # remove from item list
        for i, item in enumerate(self._key_list):
            if id(item) == key_id:
                del self._key_list[i]
                break

    def __iter__(self) -> Iterator[KT]:
        return iter(self._key_list)

    def __len__(self) -> int:
        return len(self._key_list)

    def __repr__(self) -> str:
        items = [(key, self._id_map[id(key)]) for key in self._key_list]
        return f"{self.__class__.__name__}({dict(items)})"

    def clear(self) -> None:
        self._id_map.clear()
        self._key_list.clear()


class BaseArray[TomlkitT: list, ItemT](
    MutableSequence[ItemT], BaseTomlElement[TomlkitT]
):
    """
    Base array of either primitive types or tables.
    """

    _item_map: ItemMapping[Any, Any]
    """
    Mapping of tomlkit object to this array's item object, which may be a wrapper
    object.
    """

    def __init__(self):
        self._item_map = ItemMapping()

    @overload
    def __getitem__(self, index: int) -> ItemT: ...

    @overload
    def __getitem__(self, index: slice) -> list[ItemT]: ...

    def __getitem__(self, index: int | slice) -> ItemT | list[ItemT]:
        if isinstance(index, int):
            item_obj = self._tomlkit_obj[index]
            return self._item_map.get(item_obj, item_obj)
        else:
            assert isinstance(index, slice)
            item_objs = self._tomlkit_obj[index]
            return [self._item_map.get(o, o) for o in item_objs]

    @overload
    def __setitem__(self, index: int, value: ItemT) -> None: ...

    @overload
    def __setitem__(self, index: slice, value: Iterable[ItemT]) -> None: ...

    def __setitem__(self, index: int | slice, value: ItemT | Iterable[ItemT]) -> None:
        if isinstance(index, int):
            self._tomlkit_obj[index] = self._normalize_item(cast(ItemT, value))
        else:
            assert isinstance(index, slice)
            assert isinstance(value, Iterable)
            self._tomlkit_obj[index] = self._normalize_items(
                cast(Iterable[ItemT], value)
            )

    def __delitem__(self, index: int | slice) -> None:
        item_obj = self._tomlkit_obj[index]
        if item_obj in self._item_map:
            del self._item_map[item_obj]
        del self._tomlkit_obj[index]

    def __len__(self) -> int:
        return len(self._tomlkit_obj)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({list(self)})"

    def __eq__(self, other: Any) -> bool:
        return list(self) == other

    def insert(self, index: int, value: ItemT) -> None:
        self._tomlkit_obj.insert(index, value)

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

        obj = cls()

        # get raw values
        item_values = cls._get_item_values(tomlkit_obj)

        # create initial mappings from tomlkit items to wrapper items
        if issubclass(item_cls, BaseTomlElement):
            for item_obj in item_values:
                obj._item_map[item_obj] = item_cls._from_tomlkit_obj(
                    item_obj, annotation=item_type
                )

        return obj

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
        if isinstance(item, BaseTomlElement):
            item_obj = item._tomlkit_obj
            self._item_map[item_obj] = item
            return item_obj
        else:
            return item

    def _normalize_items(self, items: Iterable[ItemT]) -> list[Any]:
        """
        Normalize inputs to tomlkit object.
        """
        return [self._normalize_item(i) for i in items]


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

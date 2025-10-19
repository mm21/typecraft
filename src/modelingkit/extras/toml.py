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
from typing import (
    Any,
    Iterable,
    MutableMapping,
    MutableSequence,
    Self,
    cast,
    overload,
)

import tomlkit
from tomlkit import TOMLDocument
from tomlkit.items import (
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

from ..inspecting.annotations import Annotation
from ..inspecting.classes import extract_type_param
from ..models import BaseModel, FieldInfo, ModelConfig
from ..validating import TypedValidator, ValidationContext

__all__ = [
    "BaseDocumentWrapper",
    "BaseTableWrapper",
    "BaseInlineTableWrapper",
    "ArrayItemType",
    "ArrayWrapper",
    "TableArrayWrapper",
]

type BuiltinType = str | int | float | bool | datetime.date | datetime.time | datetime.datetime

type TomlkitArrayItemType = String | Integer | Float | Bool | Date | Time | DateTime | InlineTable | Array

type ArrayItemType = BuiltinType | TomlkitArrayItemType | BaseInlineTableWrapper | ArrayWrapper
"""
Types which can be used as array items.
"""

type ItemType = Item | BaseTomlWrapper
"""
Types which can be normalized to a tomlkit item.
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

    @abstractmethod
    def _create_tomlkit_obj(self) -> TomlkitT:
        """
        Create corresponding tomlkit object.
        """
        ...

    @abstractmethod
    def _propagate_tomlkit_obj(self, tomlkit_obj: TomlkitT):
        """
        Propagate this wrapper's state to newly created tomlkit object.
        """
        ...

    @classmethod
    def _finalize_obj(
        cls,
        tomlkit_obj: TomlkitT,
        obj: Self,
    ) -> Self:
        assert isinstance(tomlkit_obj, cls._get_tomlkit_cls())
        obj._set_tomlkit_obj(tomlkit_obj, bypass_propagate=True)
        return obj

    @classmethod
    def _get_tomlkit_cls(cls) -> type[TomlkitT]:
        """
        Get corresponding tomlkit class.
        """
        tomlkit_cls = extract_type_param(cls, BaseTomlWrapper)
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
    BaseModel, BaseTomlWrapper[TomlkitT]
):
    """
    Base container for items in a document or table. Upon reading a TOML file via
    `tomlkit`, coerces values from `tomlkit` types to the corresponding type
    in this package.

    Only primitives (`str`, `int`, `float`, `bool`, `date`, `time`, `datetime`),
    `tomlkit` item types, and `tomlkit` wrapper types are allowed as fields.
    """

    model_config = ModelConfig(validate_on_assignment=True)

    def model_get_converters(self) -> tuple[TypedValidator[Any], ...]:
        return CONVERTERS

    def model_pre_validate(self, field_info: FieldInfo, value: Any) -> Any:
        value_ = _normalize_value(value) if value is not None else None

        # if applicable, propagate to wrapped tomlkit object
        if self._tomlkit_obj:
            self._propagate_field(self._tomlkit_obj, field_info, value_)

        return value_

    @classmethod
    def _from_tomlkit_obj(
        cls,
        tomlkit_obj: TomlkitT,
    ) -> Self:
        obj = cls.model_load(tomlkit_obj, by_alias=True)
        return cls._finalize_obj(tomlkit_obj, obj)

    def _propagate_tomlkit_obj(self, tomlkit_obj: TomlkitT):
        for name, field_info in self.model_fields.items():
            self._propagate_field(tomlkit_obj, field_info, getattr(self, name))

    def _propagate_field(
        self, tomlkit_obj: TomlkitT, field_info: FieldInfo, value: Any
    ):
        """
        Propagate field to this container's tomlkit object.
        """
        field_name = field_info.get_name(by_alias=True)

        if value is None:
            # propagate delete
            if field_name in tomlkit_obj:
                del tomlkit_obj[field_name]
        else:
            # propagate item
            tomlkit_obj[field_name] = _normalize_item(value)


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


class BaseArrayWrapper[TomlkitT: list, ItemT: ArrayItemType | BaseTableWrapper](
    MutableSequence[ItemT], BaseTomlWrapper[TomlkitT]
):
    """
    Base array of either primitive types or tables.
    """

    __list: list[ItemType]
    """
    List of ItemT values normalized to tomlkit objects or wrappers.
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
        return cast(ItemT | list[ItemT], self.__list[index])

    @overload
    def __setitem__(self, index: int, value: ItemT): ...

    @overload
    def __setitem__(self, index: slice, value: Iterable[ItemT]): ...

    def __setitem__(self, index: int | slice, value: ItemT | Iterable[ItemT]):
        if isinstance(index, int):
            value_ = _normalize_value(value)
            self.__list[index] = value_
            if self._tomlkit_obj:
                self._tomlkit_obj[index] = _normalize_item(value_)
        else:
            assert isinstance(index, slice)
            assert isinstance(value, Iterable)
            value_ = _normalize_values(value)
            self.__list[index] = value_
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
        self.__list.insert(index, value_)
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
    def _from_tomlkit_obj_with_annotation(
        cls,
        tomlkit_obj: TomlkitT,
        annotation: Annotation,
        context: ValidationContext,
    ) -> Self:
        assert len(annotation.arg_annotations) == 1
        item_type = annotation.arg_annotations[0]

        # get items and validate
        items = cls._get_item_values(tomlkit_obj)
        validated_items = [context.validate(o, item_type) for o in items]

        obj = cls(validated_items)
        return cls._finalize_obj(tomlkit_obj, obj)

    def _propagate_tomlkit_obj(self, tomlkit_obj: TomlkitT):
        assert len(tomlkit_obj) == 0
        tomlkit_obj += _normalize_items(self.__list)


class ArrayWrapper[ItemT: ArrayItemType](BaseArrayWrapper[Array, ItemT]):
    """
    Array of primitive types.
    """

    def _create_tomlkit_obj(self) -> Array:
        return Array([], Trivia())

    @staticmethod
    def _get_item_values(tomlkit_obj: Array) -> list[Any]:
        return tomlkit_obj.value


class TableArrayWrapper[ItemT: BaseTableWrapper](BaseArrayWrapper[AoT, ItemT]):
    """
    Array of (non-inline) tables.
    """

    def _create_tomlkit_obj(self) -> AoT:
        return AoT([])

    @staticmethod
    def _get_item_values(tomlkit_obj: AoT) -> list[Any]:
        return tomlkit_obj.body


def _normalize_value(value: Any) -> ItemType:
    """
    Normalize value to `BaseTomlWrapper` or tomlkit item.
    """
    if isinstance(value, (BaseTomlWrapper, Item)):
        return value
    else:
        return tomlkit.item(value)


def _normalize_values(values: Iterable[Any]) -> list[ItemType]:
    """
    Normalize values to `BaseTomlWrapper`s or items.
    """
    return [_normalize_value(v) for v in values]


def _normalize_item(obj: ItemType) -> Item:
    """
    Normalize object to tomlkit item.
    """
    if isinstance(obj, BaseTomlWrapper):
        return obj.tomlkit_obj
    else:
        assert isinstance(obj, Item)
        return obj


def _normalize_items(objs: Iterable[ItemType]) -> list[Item]:
    """
    Normalize objects to tomlkit items.
    """
    return [_normalize_item(o) for o in objs]


def convert_table(
    obj: Any, annotation_info: Annotation, _: ValidationContext
) -> BaseTableWrapper | BaseInlineTableWrapper:
    type_ = annotation_info.concrete_type
    assert issubclass(type_, (BaseTableWrapper, BaseInlineTableWrapper))
    return type_._from_tomlkit_obj(obj)


def convert_array(
    obj: Any, annotation_info: Annotation, context: ValidationContext
) -> ArrayWrapper | TableArrayWrapper:
    type_ = annotation_info.concrete_type
    assert issubclass(type_, (ArrayWrapper, TableArrayWrapper))
    return type_._from_tomlkit_obj_with_annotation(obj, annotation_info, context)


CONVERTERS = (
    TypedValidator(Table, BaseTableWrapper, func=convert_table),
    TypedValidator(InlineTable, BaseInlineTableWrapper, func=convert_table),
    TypedValidator(Array, ArrayWrapper, func=convert_array),
    TypedValidator(AoT, TableArrayWrapper, func=convert_array),
)

"""
Layer to map TOML files (via `tomlkit`) to/from Pydantic models.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date as Date
from datetime import datetime as DateTime
from datetime import time as Time
from functools import cached_property
from pathlib import Path
from typing import Any, Mapping, Self, cast, get_args, get_origin

import tomlkit
import tomlkit.items
from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator
from pydantic.fields import FieldInfo

from ..typing.generics import get_type_param

type ArrayItemType = str | int | float | bool | Date | Time | DateTime | BaseInlineTable | Array
"""
Types which can be used as fields of array items.
"""


class BaseTomlElement[TomlkitT](ABC):
    """
    Abstracts a TOML element corresponding to a type from `tomlkit`.
    """

    _tomlkit_obj: TomlkitT
    """
    Corresponding object from `tomlkit`, either extracted upon load or newly created.
    """

    _field_info: FieldInfo | None
    """
    Field info, only applicable if element is nested (i.e. not a document).
    """

    @classmethod
    @abstractmethod
    def _coerce(
        cls,
        tomlkit_obj: TomlkitT,
        field_info: FieldInfo | None = None,
        annotation: type[Any] | None = None,
    ) -> Self: ...

    @classmethod
    def _from_tomlkit_obj(
        cls,
        tomlkit_obj: TomlkitT,
        field_info: FieldInfo | None = None,
        annotation: type[Any] | None = None,
    ) -> Self:
        tomlkit_cls = cls._get_tomlkit_cls()
        assert isinstance(
            tomlkit_obj, tomlkit_cls
        ), f"Object has invalid type: expected {tomlkit_cls}, got {type(tomlkit_obj)} ({tomlkit_obj})"

        obj = cls._coerce(tomlkit_obj, field_info, annotation)
        obj._tomlkit_obj = tomlkit_obj
        obj._field_info = field_info
        return obj

    @classmethod
    def _get_tomlkit_cls(cls) -> type[TomlkitT]:
        """
        Get corresponding class from `tomlkit`.
        """
        tomlkit_cls = get_type_param(cls, BaseTomlElement)
        assert tomlkit_cls, f"Could not get type param for {cls}"
        return tomlkit_cls

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

        field_info = cls.model_fields.get(info.field_name)
        assert field_info

        annotation = field_info.annotation
        assert annotation

        field_cls = get_origin(annotation) or annotation

        # coerce value if type is element
        if issubclass(field_cls, BaseTomlElement):
            return field_cls._from_tomlkit_obj(value, field_info, annotation)

        return value

    @classmethod
    def _coerce(
        cls,
        tomlkit_obj: TomlkitT,
        field_info: FieldInfo | None = None,
        annotation: type[Any] | None = None,
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


class BaseTable(BaseContainer[tomlkit.items.Table]):
    """
    Abstracts a table with nested primitive types or other tables.
    """


class BaseInlineTable(BaseContainer[tomlkit.items.InlineTable]):
    """
    Abstracts an inline table with nested primitive types.
    """


class BaseArray[TomlkitT, ItemT](list[ItemT], BaseTomlElement[TomlkitT]):
    """
    Base array of either primitive types or tables.
    """

    @staticmethod
    @abstractmethod
    def _get_item_values(tomlkit_obj: TomlkitT) -> list[Any]:
        """
        Get raw values from this tomlkit object.
        """
        ...

    @classmethod
    def _coerce(
        cls,
        tomlkit_obj: TomlkitT,
        field_info: FieldInfo | None = None,
        annotation: type[Any] | None = None,
    ) -> Self:
        assert annotation, "No annotation"

        items: list[ItemT] = []

        # get type with which this array is parameterized
        item_cls, item_type = cls._get_item_cls(annotation)

        # get raw values
        item_values = cls._get_item_values(tomlkit_obj)

        if issubclass(item_cls, BaseTomlElement):
            for item_obj in item_values:
                items.append(item_cls._from_tomlkit_obj(item_obj, annotation=item_type))
        else:
            items = item_values

        return cls(items)

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


@dataclass(kw_only=True)
class ArrayInfo:
    """
    Extra metadata for arrays. Set by typing the field as:

    ```python
    my_array: Annotated[Array, ArrayInfo(multiline=True)]
    ```
    """

    multiline: bool | None = None
    """
    Whether the array is multiline; preserves the original state if `None`.
    """


class Array[ItemT: ArrayItemType](BaseArray[tomlkit.items.Array, ItemT]):
    """
    Array of primitive types.
    """

    @staticmethod
    def _get_item_values(tomlkit_obj: tomlkit.items.Array) -> list[Any]:
        return tomlkit_obj.value

    @cached_property
    def _array_info(self) -> ArrayInfo:
        info = (
            next(
                (m for m in self._field_info.metadata if isinstance(m, ArrayInfo)), None
            )
            if self._field_info
            else None
        )
        return info or ArrayInfo()


class TableArray[TableT: BaseTable](BaseArray[tomlkit.items.AoT, TableT]):
    """
    Array of tables.
    """

    @staticmethod
    def _get_item_values(tomlkit_obj: tomlkit.items.AoT) -> list[Any]:
        return tomlkit_obj.body

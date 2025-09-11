"""
Layer to map TOML files (via `tomlkit`) to/from Pydantic models.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date as Date
from datetime import datetime as DateTime
from datetime import time as Time
from pathlib import Path
from typing import Any, Mapping, Self, get_origin

import tomlkit
import tomlkit.items
from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator

from ..typing.generics import extract_type_param

type PrimitiveType = str | int | float | bool | Date | Time | DateTime
"""
Primitive type which can be used as a container field.
"""


class BaseTomlElement[TomlkitT](ABC):
    """
    Abstracts a TOML element corresponding to a type from `tomlkit`.
    """

    _tomlkit_cls: type[TomlkitT]
    """
    Corresponding class from `tomlkit`.
    """

    _tomlkit_obj: TomlkitT
    """
    Corresponding object from `tomlkit`, either extracted upon load or newly created.
    """

    def __init_subclass__(cls):
        super().__init_subclass__()

        if tomlkit_cls := extract_type_param(cls, BaseTomlElement):
            cls._tomlkit_cls = tomlkit_cls

    @classmethod
    @abstractmethod
    def _coerce(cls, tomlkit_obj: TomlkitT) -> Self: ...

    @classmethod
    def _create(cls, tomlkit_obj: TomlkitT) -> Self:
        obj = cls._coerce(tomlkit_obj)
        obj._tomlkit_obj = tomlkit_obj
        return obj


class BasePrimitiveArray[ItemT: PrimitiveType](
    list[ItemT], BaseTomlElement[tomlkit.items.Array]
):
    """
    Base array of primitive types.
    """

    _default_multiline: bool | None = None
    """
    Default value for `tomlkit`'s multiline state for this array, only applicable if
    newly created.
    """

    @classmethod
    def _coerce(cls, tomlkit_obj: tomlkit.items.Array) -> Self:
        return cls(tomlkit_obj.value)


class PrimitiveArray[ItemT: PrimitiveType](BasePrimitiveArray[ItemT]):
    """
    Array of primitive types, using the multiline state from the underlying `tomlkit`
    object.
    """


class MultilinePrimitiveArray[ItemT: PrimitiveType](PrimitiveArray[ItemT]):
    """
    Array of primitive types, ensuring the multiline state from the underlying `tomlkit`
    object is enabled.
    """

    _default_multiline = True


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

        field = cls.model_fields.get(info.field_name)
        assert field

        annotation = field.annotation
        assert annotation

        origin = get_origin(annotation)

        if origin:
            field_type = origin
        else:
            field_type = annotation

        # coerce value if type is element
        if issubclass(field_type, BaseTomlElement):
            assert isinstance(value, field_type._tomlkit_cls)  # type: ignore
            return field_type._create(value)

        # TODO: sanity check: ensure field is primitive

        return value

    @classmethod
    def _coerce(cls, tomlkit_obj: TomlkitT) -> Self:
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
        return cls._create(tomlkit.loads(string))

    def dump(self, file: Path, /):
        # TODO
        ...

    def dumps(self) -> str:
        # TODO
        ...


class BaseTable(BaseContainer[tomlkit.items.Table]):
    """
    Abstracts a TOML table.

    Saves the parsed `tomlkit.items.Table` upon loading so it can be updated upon
    storing, preserving item attributes like whether arrays are multiline.
    """


class BaseInlineTable(BaseContainer[tomlkit.items.InlineTable]):
    """
    Abstracts an inline table.
    """

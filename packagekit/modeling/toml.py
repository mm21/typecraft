"""
Layer to map TOML files (via `tomlkit`) to/from Pydantic models.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Self

import tomlkit
import tomlkit.items
from pydantic import BaseModel, ConfigDict, PrivateAttr, ValidationInfo, field_validator


class BaseTomlModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BaseContainer[ContainerT: Mapping](BaseTomlModel):
    """
    Container for items in a document or table. Handles validation and serialization,
    coercing to/from `BaseTable` subclasses and `tomlkit` types like
    `tomlkit.items.Array`.
    """

    __tomlkit_container: ContainerT = PrivateAttr()

    @field_validator("*", mode="before", check_fields=False)
    @classmethod
    def validate_field(cls, val: Any, info: ValidationInfo) -> Any:
        assert info.field_name

        field = cls.model_fields.get(info.field_name)
        assert field

        field_type = field.annotation
        assert field_type

        if issubclass(field_type, BaseTable):
            assert isinstance(val, tomlkit.items.Table)
            return cls._coerce_table(val, field_type)
        if issubclass(field_type, BaseInlineTable):
            assert isinstance(val, tomlkit.items.InlineTable)
            return cls._coerce_inline_table(val, field_type)

        return val

    @classmethod
    def _from_container(cls, container: ContainerT) -> Self:
        """
        Extract model fields from container and return instance of this model with
        the original container stored.
        """
        fields: dict[str, Any] = {}

        for name in cls.model_fields.keys():
            if name in container:
                fields[name] = container[name]

        obj = cls(**fields)
        obj._set_container(container)

        return obj

    @classmethod
    def _coerce_table[T: BaseTable](
        cls, val: tomlkit.items.Table, table_cls: type[T]
    ) -> T:
        return table_cls._from_container(val)

    @classmethod
    def _coerce_inline_table[T: BaseInlineTable](
        cls, val: tomlkit.items.InlineTable, inline_table_cls: type[T]
    ) -> T:
        # TODO
        ...

    def _set_container(self, container: ContainerT):
        """
        Set tomlkit container for later use.
        """
        self.__tomlkit_container = container

    def _update_container(self):
        """
        Update tomlkit container with values from model, preserving any existing values.
        """
        # TODO
        ...


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
        return cls._from_container(tomlkit.loads(string))

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

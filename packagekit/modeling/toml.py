"""
Layer to map TOML files (via `tomlkit`) to/from Pydantic models.
"""

from __future__ import annotations

from pathlib import Path
from typing import Self

from pydantic import BaseModel


class BaseContainer(BaseModel):
    """
    Container for items in a document or table. Handles validation and serialization,
    coercing to/from `BaseTable` subclasses and `tomlkit` types like
    `tomlkit.items.Array`.
    """


class BaseDocument(BaseContainer):
    """
    Abstracts a TOML document.

    Saves the parsed `tomlkit.toml_document.TOMLDocument` upon loading so it can be
    updated upon storing, preserving item attributes like whether arrays are multiline.
    """

    @classmethod
    def load(cls, file: Path, /) -> Self:
        """
        Load this document from a file.
        """
        # TODO
        ...


class BaseTable(BaseContainer):
    """
    Abstracts a TOML table.

    Saves the parsed `tomlkit.items.Table` upon loading so it can be updated upon
    storing, preserving item attributes like whether arrays are multiline.
    """

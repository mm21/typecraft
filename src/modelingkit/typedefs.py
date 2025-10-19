"""
Basic definitions for type-based converting.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import (
    Generator,
    Literal,
)

from .inspecting.annotations import flatten_union

__all__ = [
    "VarianceType",
]


type VarianceType = Literal["contravariant", "invariant"]
"""
Variance supported by a converter.
"""

type ValueCollectionType = list | tuple | set | frozenset | range | Generator
"""
Types convertible to lists, tuples, and sets; collections which contain values
rather than key-value mappings.
"""

type CollectionType = ValueCollectionType | Mapping
"""
Types convertible to collection types.
"""

VALUE_COLLECTION_TYPES = flatten_union(ValueCollectionType)
COLLECTION_TYPES = flatten_union(CollectionType)

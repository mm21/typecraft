"""
Basic definitions for type-based converting.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence, Set
from typing import (
    Any,
    Generator,
)

from .inspecting.annotations import Annotation, flatten_union

type ValueCollectionTargetType = Sequence | Set | tuple
"""
Collections which contain values rather than key-value mappings.
"""

type ValueCollectionSourceType = ValueCollectionTargetType | range | Generator[
    Any, None, None
]
"""
Types convertible to `ValueCollectionType`.
"""

type CollectionTargetType = ValueCollectionTargetType | Mapping
"""
Superset of all collection types.
"""

type CollectionSourceType = ValueCollectionSourceType | Mapping
"""
Superset of all types convertible to `CollectionType`.
"""


def _extract_types(type_: Any) -> tuple[type, ...]:
    """
    Extract concrete types from annotation.
    """
    types = flatten_union(type_)
    return tuple(Annotation(t).concrete_type for t in types)


VALUE_COLLECTION_TARGET_TYPES = _extract_types(ValueCollectionTargetType)
VALUE_COLLECTION_SOURCE_TYPES = _extract_types(ValueCollectionSourceType)
COLLECTION_TARGET_TYPES = _extract_types(CollectionTargetType)
COLLECTION_SOURCE_TYPES = _extract_types(CollectionSourceType)

COLLECTION_TARGET_TYPE_EXCEPTIONS = (str, bytes, bytearray, memoryview)
"""
Collection target types which shouldn't be recursed into.
"""

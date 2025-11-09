"""
Basic definitions for type-based converting.
"""

from __future__ import annotations

from typing import (
    Any,
    Generator,
)

from .inspecting.annotations import Annotation, flatten_union

type ValueCollectionType = list | tuple | set | frozenset | range | Generator
"""
Collections which contain values rather than key-value mappings.
"""


type CollectionType = ValueCollectionType | dict
"""
Superset of all collection types.
"""


def _extract_types(type_: Any) -> tuple[type, ...]:
    """
    Extract concrete types from annotation.
    """
    types = flatten_union(type_)
    return tuple(Annotation(t).concrete_type for t in types)


VALUE_COLLECTION_TYPES = _extract_types(ValueCollectionType)
COLLECTION_TYPES = _extract_types(CollectionType)

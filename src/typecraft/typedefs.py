"""
Basic definitions for type-based converting.
"""

from __future__ import annotations

from dataclasses import Field
from typing import (
    Any,
    ClassVar,
    Generator,
    Protocol,
    runtime_checkable,
)

from .inspecting.annotations import Annotation, flatten_union

type ValueCollectionType = list | tuple | set | frozenset | range | Generator
"""
Types convertible to builtin collections which contain values rather than key-value
mappings.
"""


type CollectionType = ValueCollectionType | dict
"""
Superset of all types convertible to builtin collections.
"""


@runtime_checkable
class DataclassProtocol(Protocol):
    """
    Runtime-checkable protocol for dataclasses.
    """

    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]


def _extract_types(type_: Any) -> tuple[type, ...]:
    """
    Extract concrete types from annotation.
    """
    types = flatten_union(type_)
    return tuple(Annotation(t).concrete_type for t in types)


VALUE_COLLECTION_TYPES = _extract_types(ValueCollectionType)
COLLECTION_TYPES = _extract_types(CollectionType)

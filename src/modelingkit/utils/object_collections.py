"""
Collections which normally operate on hashable objects only (mappings and sets), but
supporting arbitrary Python objects including non-hashable ones like lists.
"""

from typing import Iterator, MutableMapping

__all__ = [
    "ObjectMapping",
]


class ObjectMapping[KT, VT](MutableMapping[KT, VT]):
    """
    Maintains a mapping from arbitrary objects to other objects using id of keys to
    support non-hashable keys. Keeps a mapping of the key objects to ensure they don't
    get garbage collected.
    """

    __obj_map: dict[int, tuple[KT, VT]]
    """
    Mapping of key id to tuple of (key, object). The key object is stored to maintain
    its reference count; if it gets deleted, its id could get assigned to a different
    object.
    """

    def __init__(self):
        self.__obj_map = {}

    def __getitem__(self, key: KT) -> VT:
        key_id = id(key)
        if key_id not in self.__obj_map:
            raise KeyError(key)
        _, value = self.__obj_map[key_id]
        return value

    def __setitem__(self, key: KT, value: VT) -> None:
        self.__obj_map[id(key)] = (key, value)

    def __delitem__(self, key: KT) -> None:
        key_id = id(key)

        if key_id not in self.__obj_map:
            raise KeyError(key)

        del self.__obj_map[key_id]

    def __iter__(self) -> Iterator[KT]:
        return iter(k for k, _ in self.__obj_map.values())

    def __len__(self) -> int:
        return len(self.__obj_map)

    def __repr__(self) -> str:
        items = {str(k): str(v) for k, v in self.__obj_map.values()}
        return f"{self.__class__.__name__}({items})"

    def clear(self) -> None:
        self.__obj_map.clear()

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

    __id_map: dict[int, VT]
    """
    Mapping of key id to object.
    """

    __key_map: dict[int, KT]
    """
    Mapping of key id to key object, used to maintain its reference count.
    """

    def __init__(self):
        self.__id_map = {}
        self.__key_map = {}

    def __getitem__(self, key: KT) -> VT:
        key_id = id(key)
        if key_id not in self.__id_map:
            raise KeyError(key)
        return self.__id_map[key_id]

    def __setitem__(self, key: KT, value: VT) -> None:
        key_id = id(key)
        self.__id_map[key_id] = value
        self.__key_map[key_id] = key

    def __delitem__(self, key: KT) -> None:
        key_id = id(key)

        if key_id not in self.__id_map or key_id not in self.__key_map:
            raise KeyError(key)

        del self.__id_map[key_id]
        del self.__key_map[key_id]

    def __iter__(self) -> Iterator[KT]:
        return iter(self.__key_map.values())

    def __len__(self) -> int:
        return len(self.__id_map)

    def __repr__(self) -> str:
        items = {
            str(key): str(self.__id_map[key_id])
            for key_id, key in self.__key_map.items()
        }
        return f"{self.__class__.__name__}({dict(items)})"

    def clear(self) -> None:
        self.__id_map.clear()
        self.__key_map.clear()

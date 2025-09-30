from typing import Iterator, MutableMapping


class ObjectMapping[KT, VT](MutableMapping[KT, VT]):
    """
    Maintains a mapping from arbitrary objects to other objects using id of keys to
    support non-hashable keys. Keeps a list of the key objects to ensure they don't
    get garbage collected.
    """

    __id_map: dict[int, VT]
    """
    Mapping of key id to object.
    """

    __key_list: list[KT]
    """
    List of key objects.
    """

    def __init__(self):
        self.__id_map = {}
        self.__key_list = []

    def __getitem__(self, key: KT) -> VT:
        key_id = id(key)
        if key_id not in self.__id_map:
            raise KeyError(key)
        return self.__id_map[key_id]

    def __setitem__(self, key: KT, value: VT) -> None:
        key_id = id(key)

        # if key doesn't exist, add it to item list to preserve reference
        if key_id not in self.__id_map:
            self.__key_list.append(key)

        self.__id_map[key_id] = value

    def __delitem__(self, key: KT) -> None:
        key_id = id(key)

        if key_id not in self.__id_map:
            raise KeyError(key)

        # remove from id mapping
        del self.__id_map[key_id]

        # remove from item list
        for i, item in enumerate(self.__key_list):
            if id(item) == key_id:
                del self.__key_list[i]
                break

    def __iter__(self) -> Iterator[KT]:
        return iter(self.__key_list)

    def __len__(self) -> int:
        return len(self.__key_list)

    def __repr__(self) -> str:
        items = [(key, self.__id_map[id(key)]) for key in self.__key_list]
        return f"{self.__class__.__name__}({dict(items)})"

    def clear(self) -> None:
        self.__id_map.clear()
        self.__key_list.clear()

"""
Inspecting utilities.
"""

from typing import Protocol


def safe_issubclass(cls: type, class_or_tuple: type | tuple[type, ...], /) -> bool:
    """
    `issubclass()` can raise `TypeError` in some cases, even when the arguments are
    types; handle it gracefully. Additionally handle checking a class against
    a protocol while taking attributes into consideration (not supported by
    `issubclass()`.)

    `issubclass()` has this limitation since it's messy to differentiate between
    class vs instance attributes. Here we won't differentiate between them,
    which works for most cases (like `DataclassProtocol`).
    """
    # make sure the user passed types; don't want to mask that reason for TypeError
    if not isinstance(cls, type):
        raise TypeError(f"safe_issubclass() arg 1 must be a class: {cls}")
    if (
        isinstance(class_or_tuple, tuple)
        and not all(isinstance(c, type) for c in class_or_tuple)
    ) or not isinstance(class_or_tuple, type):
        raise TypeError(
            f"safe_issubclass() arg 2 must be a class or tuple of classes: {class_or_tuple}"
        )

    try:
        is_subclass = issubclass(cls, class_or_tuple)
    except TypeError:
        # check for protocol with non-method members
        tuple_ = (
            class_or_tuple if isinstance(class_or_tuple, tuple) else (class_or_tuple,)
        )
        for c in tuple_:
            if issubclass(c, Protocol):
                protocol_attrs = getattr(c, "__protocol_attrs__", None)
                assert isinstance(protocol_attrs, set)

                # aggregate attributes from annotations (which includes type
                # hints for not-yet-set attributes), including from parent classes
                cls_attrs = set()
                for base in cls.__mro__:
                    cls_attrs.update(getattr(base, "__annotations__", {}))

                # aggregate methods using dir(), which includes parent classes
                cls_attrs.update(dir(cls))

                # check if cls has all attributes/methods defined on protocol
                if protocol_attrs <= cls_attrs:
                    return True
        return False
    else:
        return is_subclass

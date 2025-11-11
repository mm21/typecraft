"""
Inspecting utilities.
"""


def safe_issubclass(cls: type, class_or_tuple: type | tuple[type, ...], /) -> bool:
    """
    `issubclass()` can raise `TypeError` in some cases, even when the arguments are
    types; handle it and gracefully return `False`.
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
        return False

    return is_subclass

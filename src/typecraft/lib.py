"""
Library of common validators.
"""

import re

from .converting.validator import BaseValidator, ValidationFrame


class IntValidator(BaseValidator[int]):
    """
    Validates an integer against optional lt/lte/gt/gte bounds.
    """

    lt: int | None
    lte: int | None
    gt: int | None
    gte: int | None

    def __init__(
        self,
        *,
        lt: int | None = None,
        lte: int | None = None,
        gt: int | None = None,
        gte: int | None = None,
    ):
        self.lt = lt
        self.lte = lte
        self.gt = gt
        self.gte = gte

    def validate(self, obj: int, frame: ValidationFrame) -> int:
        _ = frame
        if self.lt is not None and not (obj < self.lt):
            raise ValueError(f"not < {self.lt}")
        if self.lte is not None and not (obj <= self.lte):
            raise ValueError(f"not <= {self.lte}")
        if self.gt is not None and not (obj > self.gt):
            raise ValueError(f"not > {self.gt}")
        if self.gte is not None and not (obj >= self.gte):
            raise ValueError(f"not >= {self.gte}")
        return obj


class StrValidator(BaseValidator[str]):
    """
    Validates a string against optional min/max length bounds.
    """

    min_len: int | None
    max_len: int | None

    def __init__(
        self,
        *,
        min_len: int | None = None,
        max_len: int | None = None,
    ):
        self.min_len = min_len
        self.max_len = max_len

    def validate(self, obj: str, frame: ValidationFrame) -> str:
        _ = frame
        length = len(obj)
        if self.min_len is not None and length < self.min_len:
            raise ValueError(f"length {length} < min_length {self.min_len}")
        if self.max_len is not None and length > self.max_len:
            raise ValueError(f"length {length} > max_length {self.max_len}")
        return obj


_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


class EmailValidator(BaseValidator[str]):
    """
    Validates that a string matches a basic email address pattern.
    """

    def validate(self, obj: str, frame: ValidationFrame) -> str:
        _ = frame
        if not _EMAIL_RE.match(obj):
            raise ValueError(f"invalid email address: {obj!r}")
        return obj

"""
Specific models accommodating different formats.

To use, install this package with the respective extras group, e.g. `typecraft[toml]`.
"""

# requires optional dependencies, so not rolled up
__submodules__: list[str] = []

# isort: off
# <AUTOGEN_INIT>
from .toml import (
    BaseDocument,
    BaseTable,
    BaseInlineTable,
    ArrayItemType,
    ArrayWrapper,
    AoTWrapper,
)

__all__ = [
    "BaseDocument",
    "BaseTable",
    "BaseInlineTable",
    "ArrayItemType",
    "ArrayWrapper",
    "AoTWrapper",
]
# </AUTOGEN_INIT>

"""
Utilities to inspect objects at runtime.
"""

# isort: off
# <AUTOGEN_INIT>
from .annotations import (
    ANY,
    Annotation,
    is_narrower,
    is_instance,
    is_union,
    unwrap_alias,
    split_annotated,
    normalize_annotation,
    flatten_union,
    get_concrete_type,
)
from .functions import (
    ParameterInfo,
    SignatureInfo,
)
from .generics import (
    extract_args,
    extract_arg_map,
    extract_arg,
    normalize_args,
)
from .utils import (
    robust_issubclass,
)

__all__ = [
    "ANY",
    "Annotation",
    "is_narrower",
    "is_instance",
    "is_union",
    "unwrap_alias",
    "split_annotated",
    "normalize_annotation",
    "flatten_union",
    "get_concrete_type",
    "ParameterInfo",
    "SignatureInfo",
    "extract_args",
    "extract_arg_map",
    "extract_arg",
    "normalize_args",
    "robust_issubclass",
]
# </AUTOGEN_INIT>

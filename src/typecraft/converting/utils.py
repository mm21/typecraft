from __future__ import annotations

import itertools
from collections.abc import Mapping
from typing import (
    Any,
    Generator,
    Iterable,
    Sized,
)

from ..inspecting.annotations import ANY, Annotation, extract_tuple_args
from ..inspecting.generics import extract_args
from ..types import COLLECTION_TYPES
from ._types import ERROR_SENTINEL
from .converter import BaseConversionFrame


def convert_to_list(
    obj: Iterable, frame: BaseConversionFrame, /, *, construct: bool = False
) -> list:
    """
    Convert collection to list.
    """
    target_type = frame.target_annotation.concrete_type
    assert issubclass(target_type, list)

    sized_obj = obj if isinstance(obj, Sized) else list(obj)

    # extract item annotations
    source_item_anns = _extract_value_item_anns(sized_obj, frame.source_annotation)
    target_item_ann = _extract_value_item_ann(frame.target_annotation, list)

    # create list of validated items
    converted_objs = [
        frame.recurse(
            o,
            i,
            source_annotation=(
                source_item_anns[i]
                if isinstance(source_item_anns, tuple)
                else source_item_anns
            ),
            target_annotation=target_item_ann,
        )
        for i, o in enumerate(sized_obj)
    ]

    if any(o is ERROR_SENTINEL for o in converted_objs):
        # conversions failed
        return converted_objs
    elif isinstance(obj, target_type) and all(
        o is n for o, n in zip(sized_obj, converted_objs)
    ):
        # have correct type and no conversions were done: return the original object
        return obj
    elif target_type is list:
        # have a list (not a subclass thereof): return the newly created list
        return converted_objs
    elif construct:
        # construct list subclass
        return target_type(converted_objs)

    exception = ValueError(
        f"Cannot construct instance of target type {target_type}; create a custom converter for it"
    )
    frame.append_error(obj, exception)
    return converted_objs


def convert_to_tuple(
    obj: Iterable, frame: BaseConversionFrame, /, *, construct: bool = False
) -> tuple:
    """
    Convert collection to tuple.
    """
    target_type = frame.target_annotation.concrete_type
    assert issubclass(target_type, tuple)

    # validate non-variadic tuple: input can't be set
    if (
        len(frame.target_annotation.arg_annotations)
        and frame.target_annotation.arg_annotations[-1].raw is not ...
    ):
        if isinstance(obj, (set, frozenset)):
            exception = ValueError(
                f"Can't convert from set to fixed-length tuple as items would be in random order: {obj}"
            )
            frame.append_error(obj, exception)
            return ()

    sized_obj = obj if isinstance(obj, Sized) else list(obj)

    # extract item annotations
    source_item_anns = _extract_value_item_anns(sized_obj, frame.source_annotation)
    target_item_anns = extract_tuple_args(frame.target_annotation)

    if isinstance(target_item_anns, tuple) and len(target_item_anns) != len(sized_obj):
        exception = ValueError(
            f"Tuple length mismatch: expected {len(target_item_anns)} from target annotation {frame.target_annotation}, got {len(sized_obj)}: {sized_obj}"
        )
        frame.append_error(obj, exception)
        return ()

    # create tuple of validated items
    converted_objs = tuple(
        frame.recurse(
            o,
            i,
            source_annotation=(
                source_item_anns[i]
                if isinstance(source_item_anns, tuple)
                else source_item_anns
            ),
            target_annotation=(
                target_item_anns[i]
                if isinstance(target_item_anns, tuple)
                else target_item_anns
            ),
        )
        for i, o, in enumerate(sized_obj)
    )

    if any(o is ERROR_SENTINEL for o in converted_objs):
        # conversions failed
        return converted_objs
    elif isinstance(obj, target_type) and all(
        o is v for o, v in zip(sized_obj, converted_objs)
    ):
        # have correct type and no conversions were done: return the original object
        return obj
    elif target_type is tuple:
        # have a tuple (not a subclass thereof): return the newly created tuple
        return converted_objs
    elif construct:
        return target_type(converted_objs)

    exception = ValueError(
        f"Cannot construct instance of target type {target_type}; create a custom converter for it"
    )
    frame.append_error(obj, exception)
    return converted_objs


def convert_to_set(
    obj: Iterable, frame: BaseConversionFrame, /, *, construct: bool = False
) -> set | frozenset:
    """
    Convert collection to set.
    """
    target_type = frame.target_annotation.concrete_type
    assert issubclass(target_type, (set, frozenset))

    sized_obj = obj if isinstance(obj, Sized) else list(obj)

    # extract item annotations
    source_item_anns = _extract_value_item_anns(sized_obj, frame.source_annotation)
    target_item_ann = _extract_value_item_ann(frame.target_annotation, set)

    # create set of validated items
    converted_objs = {
        frame.recurse(
            o,
            i,
            source_annotation=(
                source_item_anns[i]
                if isinstance(source_item_anns, tuple)
                else source_item_anns
            ),
            target_annotation=target_item_ann,
        )
        for i, o in enumerate(sized_obj)
    }

    if any(o is ERROR_SENTINEL for o in converted_objs):
        # conversions failed
        return converted_objs
    elif isinstance(obj, target_type):
        obj_ids = {id(o) for o in sized_obj}
        if all(id(o) in obj_ids for o in converted_objs):
            # have correct type and no conversions were done: return the original object
            return obj
    if target_type in (set, frozenset):
        # have a set (not a subclass thereof): return the newly created set
        return converted_objs if target_type is set else frozenset(converted_objs)
    elif construct:
        return target_type(converted_objs)

    exception = ValueError(
        f"Cannot construct instance of target type {target_type}; create a custom converter for it"
    )
    frame.append_error(obj, exception)
    return converted_objs


def convert_to_dict(
    obj: Mapping, frame: BaseConversionFrame, /, *, construct: bool = False
) -> dict:
    """
    Convert mapping to dict.
    """
    target_type = frame.target_annotation.concrete_type
    assert issubclass(target_type, dict)

    # extract item annotations
    source_key_ann, source_value_ann = _extract_mapping_item_ann(
        frame.source_annotation, default=ANY
    )
    target_key_ann, target_value_ann = _extract_mapping_item_ann(
        frame.target_annotation
    )

    # create dict of validated items
    converted_objs = {
        frame.recurse(
            k,
            f"key[{i}]",
            source_annotation=source_key_ann,
            target_annotation=target_key_ann,
        ): frame.recurse(
            v,
            str(k),
            source_annotation=source_value_ann,
            target_annotation=target_value_ann,
        )
        for i, (k, v) in enumerate(obj.items())
    }

    if any(
        o is ERROR_SENTINEL
        for o in itertools.chain(converted_objs.keys(), converted_objs.values())
    ):
        # conversions failed
        return converted_objs
    elif isinstance(obj, target_type) and all(
        k_obj is k_conv and obj[k_obj] is converted_objs[k_conv]
        for k_obj, k_conv in zip(obj, converted_objs)
    ):
        # have correct type and no conversions were done; return the original object
        return obj
    elif target_type is dict:
        # have a dict (not a subclass thereof), return the newly created dict
        return converted_objs
    elif construct:
        return target_type(converted_objs)

    exception = ValueError(
        f"Cannot construct instance of target type {target_type}; create a custom converter for it"
    )
    frame.append_error(obj, exception)
    return converted_objs


def select_ann_from_union(obj: Any, union: Annotation) -> Annotation:
    """
    Select the annotation from the union which matches the given object. At this point
    this should always succeed; the object was previously confirmed to match the
    annotation.
    """
    assert union.is_union
    ann = next(
        (a for a in union.arg_annotations if a.check_instance(obj, recurse=False)),
        None,
    )
    assert ann
    if ann.is_union:
        return select_ann_from_union(obj, ann)
    return ann


def _extract_value_item_anns(
    obj: Sized, ann: Annotation
) -> Annotation | tuple[Annotation, ...]:
    """
    Extract item annotations for each element in the collection.

    - Returns `Annotation` if the annotation applies to each item in obj
    - Returns `tuple[Annotation, ...]` if obj is a fixed-length tuple
    """
    if issubclass(ann.concrete_type, tuple):
        source_args = extract_tuple_args(ann)
        if isinstance(source_args, tuple) and len(obj) != len(source_args):
            # TODO: append to errors in frame and return ERROR_SENTINEL
            raise ValueError(
                f"Tuple length mismatch: expected {len(source_args)} from annotation {ann}, got {len(obj)}: {obj}"
            )
        return source_args
    else:
        # determine which collection type this is a subclass of
        collection_cls = next(
            (t for t in COLLECTION_TYPES if issubclass(ann.concrete_type, t)), None
        )
        assert collection_cls
        return _extract_value_item_ann(ann, collection_cls, default=ANY)


def _extract_value_item_ann(
    ann: Annotation, base_cls: type, default: Annotation | None = None
) -> Annotation:
    """
    Extract item annotation for non-tuple value collection.
    """
    # handle special cases
    if issubclass(ann.concrete_type, Generator):
        return ann.arg_annotations[0] if len(ann.arg_annotations) else ANY
    if issubclass(ann.concrete_type, range):
        return Annotation(int)

    # extract item annotation from collection
    args = extract_args(ann.raw, base_cls)
    assert len(args) <= 1

    if len(args) == 1:
        return Annotation(args[0])

    if default:
        return default

    raise TypeError(f"Could not find item annotation of collection {ann}")


def _extract_mapping_item_ann(
    ann: Annotation, default: Annotation | None = None
) -> tuple[Annotation, Annotation]:
    """
    Extract item annotations as (key annotation, value annotation) for mapping
    collection.
    """
    args = extract_args(ann.raw, dict)
    assert len(args) in {0, 2}

    if len(args) == 2:
        return Annotation(args[0]), Annotation(args[1])

    if default:
        return default, default

    raise TypeError(f"Could not find item annotation of dict {ann}")

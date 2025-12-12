from __future__ import annotations

import dataclasses
from dataclasses import MISSING, dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Literal,
    cast,
    get_type_hints,
    overload,
)

from ..adapter import Adapter
from ..converting.converter import BaseConverter
from ..converting.serializer import (
    BaseSerializer,
    JsonSerializableType,
    SerializerRegistry,
)
from ..converting.validator import BaseValidator, ValidatorRegistry
from ..inspecting.annotations import Annotation
from ..inspecting.functions import SignatureInfo

if TYPE_CHECKING:
    from .base import BaseModel

__all__ = [
    "ValidatorModeType",
    "Field",
    "FieldMetadata",
    "FieldInfo",
    "typed_validators",
    "typed_serializers",
    "field_validator",
    "field_serializer",
]


type ValidatorModeType = Literal["before", "after"]
"""
Validator mode:

- `"before"`: Invoked before builtin validation
- `"after"`: Invoked after builtin validation
"""

type TypedConvertersType[ModelT: BaseModel, ConverterT: BaseConverter] = Callable[
    [type[ModelT]], tuple[ConverterT, ...]
]
"""
Annotates a typed converter (validator/serializer) registration method, which takes no
arguments and returns a tuple of validators/serializers.
"""

type TypedValidatorsType[ModelT: BaseModel] = TypedConvertersType[ModelT, BaseValidator]
"""
Annotates a typed validator registration method which takes no arguments and returns a
tuple of validators.
"""

type TypedSerializersType[ModelT: BaseModel] = TypedConvertersType[
    ModelT, BaseSerializer
]
"""
Annotates a typed validator registration method which takes no arguments and returns a
tuple of validators.
"""

# TODO: ValidationInfo: field_info, context, data (for cross-field validation)
type FieldValidatorType[ModelT: BaseModel] = Callable[
    [ModelT | type[ModelT], Any], Any
] | Callable[[ModelT | type[ModelT], Any, FieldInfo], Any]
"""
Annotates a field validator method which can take an optional `FieldInfo` argument.

Can decorate an instance method or classmethod.
"""

# TODO: SerializationInfo: field_info, context
type FieldSerializerType[ModelT: BaseModel] = Callable[
    [ModelT, Any], JsonSerializableType
] | Callable[[ModelT, Any, FieldInfo], JsonSerializableType]
"""
Annotates a field serializer method which can take an optional `FieldInfo` argument.

Must be an instance method.
"""

# marker attribute names for storing decorator info on class
TYPED_VALIDATORS_ATTR = "__typecraft_typed_validators__"
TYPED_SERIALIZERS_ATTR = "__typecraft_typed_serializers__"
FIELD_VALIDATOR_ATTR = "__typecraft_field_validator__"
FIELD_SERIALIZER_ATTR = "__typecraft_field_serializer__"


@dataclass(kw_only=True)
class FieldMetadata:
    """
    Encapsulates metadata for a field definition.
    """

    alias: str | None = None
    """
    Field name to use when loading a dumping from/to dict.
    """

    user_metadata: Any | None = None
    """
    User-provided metadata.
    """


class FieldInfo:
    """
    Field info with annotations processed.
    """

    field: dataclasses.Field
    """
    Dataclass field.
    """

    annotation: Annotation
    """
    Annotation info.
    """

    metadata: FieldMetadata
    """
    Metadata passed to field definition.
    """

    _adapter: Adapter
    """
    Adapter object to wrap validation/serialization.
    """

    _field_validators: tuple[FieldValidatorInfo, ...]
    """
    Field-level validators registered via decorator.
    """

    _field_serializers: tuple[FieldSerializerInfo, ...]
    """
    Field-level serializers registered via decorator.
    """

    def __init__(
        self,
        field: dataclasses.Field,
        model_cls: type[BaseModel],
        *,
        validator_registry: ValidatorRegistry,
        serializer_registry: SerializerRegistry,
        field_validators: tuple[FieldValidatorInfo, ...],
        field_serializers: tuple[FieldSerializerInfo, ...],
    ):
        if not field.type:
            raise TypeError(f"Field '{field.name}' does not have an annotation")

        type_hints = get_type_hints(model_cls, include_extras=True)
        assert field.name in type_hints

        raw_annotation = type_hints[field.name]
        annotation = Annotation(raw_annotation)

        metadata = field.metadata.get("metadata") or FieldMetadata()
        assert isinstance(metadata, FieldMetadata)

        self.field = field
        self.annotation = annotation
        self.metadata = metadata
        self._field_validators = field_validators
        self._field_serializers = field_serializers
        self._adapter = Adapter(
            annotation,
            validation_params=model_cls.model_config.validation_params,
            serialization_params=model_cls.model_config.serialization_params,
            validator_registry=validator_registry,
            serializer_registry=serializer_registry,
        )

    @property
    def name(self) -> str:
        """
        Accessor for field name.
        """
        return self.field.name

    def get_name(self, *, by_alias: bool = False) -> str:
        """
        Get this field's name, optionally using its alias.
        """
        return self.metadata.alias or self.name if by_alias else self.name

    def _get_validators(
        self, *, mode: Literal["before", "after"]
    ) -> tuple[FieldValidatorInfo, ...]:
        """
        Get field validators filtered by mode.
        """
        return tuple(v for v in self._field_validators if v.mode == mode)


@dataclass(kw_only=True)
class TypedValidatorsInfo[ModelT: BaseModel]:
    """
    Stores info about a method decorated with `@typed_validators`.
    """

    func: TypedValidatorsType[ModelT]
    """
    The method that returns validators.
    """


@dataclass(kw_only=True)
class TypedSerializersInfo[ModelT: BaseModel]:
    """
    Stores info about a method decorated with `@typed_serializers`.
    """

    func: TypedSerializersType[ModelT]
    """
    The method that returns serializers.
    """


class BaseFieldConverterInfo[T: Callable]:
    """
    Common info for field validator/serializer.
    """

    func: T
    """
    Registered function.
    """

    field_names: tuple[str, ...] | None
    """
    Field names to which this converter applies, or `None` to apply to all fields.
    """

    sig: SignatureInfo
    """
    Signature of registered function.
    """

    def __init__(self, func: T, field_names: tuple[str, ...] | None):
        self.func = func
        self.field_names = field_names
        self.sig = SignatureInfo(func)

        # validate args
        args = list(self.sig.get_params(positional=True))
        if not len(args) in {2, 3}:
            raise TypeError(
                "Function {} has unexpected number of args, must be 2 or 3: got {}".format(
                    self.func, len(args)
                )
            )


class FieldValidatorInfo(BaseFieldConverterInfo[FieldValidatorType]):
    """
    Stores info about a method decorated with `@field_validator`.
    """

    mode: ValidatorModeType
    """
    Validator mode.
    """

    is_classmethod: bool
    """
    Whether this is a classmethod.
    """

    def __init__(
        self,
        func: FieldValidatorType,
        field_names: tuple[str, ...] | None,
        mode: ValidatorModeType,
        is_classmethod: bool,
    ):
        super().__init__(func, field_names)
        self.mode = mode
        self.is_classmethod = is_classmethod


class FieldSerializerInfo(BaseFieldConverterInfo[FieldSerializerType]):
    """
    Stores info about a method decorated with `@field_serializer`.
    """


@dataclass
class RegistrationInfo:
    """
    Encapsulates validator/serializer registration info.
    """

    typed_validators: list[BaseValidator]
    typed_serializers: list[BaseSerializer]
    field_validators_info: list[FieldValidatorInfo]
    field_serializers_info: list[FieldSerializerInfo]

    @classmethod
    def from_model_cls(cls, model_cls: type[BaseModel]) -> RegistrationInfo:
        """
        Get registration info from model class.
        """
        from .base import BaseModel

        typed_validators: list[BaseValidator] = []
        typed_serializers: list[BaseSerializer] = []
        field_validators_info: list[FieldValidatorInfo] = []
        field_serializers_info: list[FieldSerializerInfo] = []

        # traverse class hierarchy in reverse MRO order
        for check_cls in reversed(model_cls.mro()):

            # skip non-model classes
            if not issubclass(check_cls, BaseModel):
                continue

            # check each attribute of this class
            for attr in vars(check_cls).values():
                # extract function from classmethod if applicable
                attr = _normalize_attr(attr)

                # skip if not callable
                if not callable(attr):
                    continue

                # check for each attribute and populate lists
                if typed_validators_info := getattr(attr, TYPED_VALIDATORS_ATTR, None):
                    assert isinstance(typed_validators_info, TypedValidatorsInfo)
                    typed_validators.extend(typed_validators_info.func(check_cls))
                elif typed_serializers_info := getattr(
                    attr, TYPED_SERIALIZERS_ATTR, None
                ):
                    assert isinstance(typed_serializers_info, TypedSerializersInfo)
                    typed_serializers.extend(typed_serializers_info.func(check_cls))
                elif field_validator_info := getattr(attr, FIELD_VALIDATOR_ATTR, None):
                    assert isinstance(field_validator_info, FieldValidatorInfo)
                    field_validators_info.append(field_validator_info)
                elif field_serializer_info := getattr(attr, FIELD_VALIDATOR_ATTR, None):
                    assert isinstance(field_serializer_info, FieldSerializerInfo)
                    field_serializers_info.append(field_serializer_info)

        return RegistrationInfo(
            typed_validators,
            typed_serializers,
            field_validators_info,
            field_serializers_info,
        )


@overload
def Field[T](
    *,
    default: T,
    alias: str | None = None,
    user_metadata: Any | None = None,
    init: bool = True,
    repr: bool = True,
    hash: bool | None = None,
    compare: bool = True,
) -> T: ...


@overload
def Field[T](
    *,
    default_factory: Callable[[], T],
    alias: str | None = None,
    user_metadata: Any | None = None,
    init: bool = True,
    repr: bool = True,
    hash: bool | None = None,
    compare: bool = True,
) -> T: ...


@overload
def Field(
    *,
    alias: str | None = None,
    user_metadata: Any | None = None,
    init: bool = True,
    repr: bool = True,
    hash: bool | None = None,
    compare: bool = True,
) -> Any: ...


def Field(
    *,
    default: Any = MISSING,
    default_factory: Any = MISSING,
    alias: str | None = None,
    user_metadata: Any | None = None,
    init: bool = True,
    repr: bool = True,
    hash: bool | None = None,
    compare: bool = True,
) -> Any:
    """
    Create a new field.

    Wraps a dataclass field along with metadata.
    """
    metadata = FieldMetadata(alias=alias, user_metadata=user_metadata)
    return dataclasses.field(
        default=default,
        default_factory=default_factory,
        init=init,
        repr=repr,
        hash=hash,
        compare=compare,
        metadata={"metadata": metadata},
    )


def typed_validators[ModelT: BaseModel](
    func: TypedValidatorsType[ModelT],
) -> TypedValidatorsType[ModelT]:
    """
    Decorator to register a classmethod that returns type-based validators.
    """
    func_ = _normalize_attr(func)
    setattr(func_, TYPED_VALIDATORS_ATTR, TypedValidatorsInfo(func=func_))
    return cast(TypedValidatorsType[ModelT], func)


def typed_serializers[ModelT: BaseModel](
    func: TypedSerializersType[ModelT],
) -> TypedSerializersType[ModelT]:
    """
    Decorator to register a classmethod that returns type-based serializers.
    """
    func_ = _normalize_attr(func)
    setattr(func_, TYPED_SERIALIZERS_ATTR, TypedSerializersInfo(func=func_))
    return cast(TypedSerializersType[ModelT], func)


@overload
def field_validator[T: FieldValidatorType](
    func: T,
    /,
) -> T: ...


@overload
def field_validator[T: FieldValidatorType](
    *field_names: str,
    mode: Literal["before", "after"] = "before",
) -> Callable[[T], T]: ...


def field_validator[T: FieldValidatorType](
    func_or_name: T | str | None = None,
    *names: str,
    mode: ValidatorModeType = "before",
) -> T | Callable[[T], T]:
    """
    Decorator to register a field-level validator.

    If field names are omitted, the validator applies to all fields.
    """

    def register(
        func: T | classmethod,
        field_names: tuple[str, ...] | None = None,
    ) -> T:
        normalized_func = _normalize_attr(func)
        info = FieldValidatorInfo(
            normalized_func, field_names, mode, isinstance(func, classmethod)
        )
        setattr(normalized_func, FIELD_VALIDATOR_ATTR, info)
        return cast(T, func)

    if isinstance(func_or_name, (Callable, classmethod)):
        # called without parentheses: @field_validator
        assert len(names) == 0
        return register(func_or_name)

    # called with parentheses: @field_validator() or @field_validator("name", ...)
    all_names = (func_or_name, *names) if isinstance(func_or_name, str) else names
    assert all(isinstance(n, str) for n in all_names)

    def decorator(func: T) -> T:
        return register(func, all_names or None)

    return decorator


@overload
def field_serializer[T: FieldSerializerType](
    func: T,
    /,
) -> T: ...


@overload
def field_serializer[T: FieldSerializerType](
    *field_names: str,
) -> Callable[[T], T]: ...


def field_serializer[T: FieldSerializerType](
    func_or_name: T | str | None = None,
    *names: str,
) -> T | Callable[[T], T]:
    """
    Decorator to register a field-level serializer.

    If field names are omitted, the serializer applies to all fields.
    """

    def register(func: T, field_names: tuple[str, ...] | None = None) -> T:
        info = FieldSerializerInfo(func, field_names)
        setattr(func, FIELD_SERIALIZER_ATTR, info)
        return func

    if isinstance(func_or_name, Callable):
        # called without parentheses: @field_serializer
        assert len(names) == 0
        return register(func_or_name)

    # called with parentheses: @field_serializer() or @field_serializer("name", ...)
    all_names = (func_or_name, *names) if isinstance(func_or_name, str) else names
    assert all(isinstance(n, str) for n in all_names)

    def decorator(func: T) -> T:
        return register(func, all_names or None)

    return decorator


def _normalize_attr[T](func: T | classmethod) -> T:
    """
    Normalize attribute to extract the raw function in case of classmethod.
    """
    return func.__func__ if isinstance(func, classmethod) else func

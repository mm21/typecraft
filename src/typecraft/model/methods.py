"""
Mechanism to register validator/serializer methods.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Literal, Self, cast, overload

from ..converting.converter.base import BaseConversionFrame
from ..converting.converter.type import BaseTypeConverter
from ..converting.serializer import (
    BaseTypeSerializer,
    JsonSerializableType,
    SerializationFrame,
)
from ..converting.validator import BaseTypeValidator, ValidationFrame
from ..inspecting.functions import SignatureInfo

if TYPE_CHECKING:
    from .base import BaseModel
    from .fields import FieldInfo


__all__ = [
    "ValidatorModeType",
    "TypeValidatorsFuncType",
    "TypeSerializersFuncType",
    "FieldValidatorFuncType",
    "FieldSerializerFuncType",
    "type_validators",
    "type_serializers",
    "field_validator",
    "field_serializer",
]


# marker attribute names for storing decorator info on class
TYPED_VALIDATORS_ATTR = "__typecraft_type_validators__"
TYPED_SERIALIZERS_ATTR = "__typecraft_type_serializers__"
FIELD_VALIDATOR_ATTR = "__typecraft_field_validator__"
FIELD_SERIALIZER_ATTR = "__typecraft_field_serializer__"


type ValidatorModeType = Literal["before", "after"]
"""
Validator mode:

- `"before"`: Invoked before builtin validation
- `"after"`: Invoked after builtin validation
"""

type TypeConvertersFuncType[
    ModelT: BaseModel, ConverterT: BaseTypeConverter
] = Callable[[type[ModelT]], tuple[ConverterT, ...]]
"""
Annotates a type-based converter (validator/serializer) registration method, which takes
no arguments and returns a tuple of validators/serializers.
"""

type BoundTypeConvertersFuncType[ConverterT: BaseTypeConverter] = Callable[
    [], tuple[ConverterT, ...]
]
"""
Annotates a bound type-based converter registration method.
"""

type TypeValidatorsFuncType[ModelT: BaseModel] = TypeConvertersFuncType[
    ModelT, BaseTypeValidator
]
"""
Annotates a type-based validator registration method which takes no arguments and
returns a tuple of validators.
"""

type BoundTypeValidatorsFuncType = BoundTypeConvertersFuncType[BaseTypeValidator]
"""
Annotates a bound type-based validator registration method.
"""

type TypeSerializersFuncType[ModelT: BaseModel] = TypeConvertersFuncType[
    ModelT, BaseTypeSerializer
]
"""
Annotates a type-based validator registration method which takes no arguments and
returns a tuple of validators.
"""

type BoundTypeSerializersFuncType = BoundTypeConvertersFuncType[BaseTypeSerializer]
"""
Annotates a bound type-based serializer registration method.
"""

type FieldValidatorFuncType[ModelT: BaseModel] = Callable[
    [ModelT | type[ModelT], Any], Any
] | Callable[[ModelT | type[ModelT], Any, ValidationInfo], Any]
"""
Annotates a field validator method which can take an optional `ValidationInfo` argument.

Can decorate an instance method or classmethod.
"""

type BoundFieldValidatorFuncType = Callable[[Any], Any] | Callable[
    [Any, ValidationInfo], Any
]
"""
Annotates a bound field validator method.
"""

type FieldSerializerFuncType[ModelT: BaseModel] = Callable[
    [ModelT, Any], JsonSerializableType
] | Callable[[ModelT, Any, SerializationInfo], JsonSerializableType]
"""
Annotates a field serializer method which can take an optional `SerializationInfo`
argument.

Must be an instance method.
"""

type BoundFieldSerializerFuncType = Callable[[Any], Any] | Callable[
    [Any, SerializationInfo], Any
]
"""
Annotates a bound field validator method.
"""


@dataclass
class BaseConversionInfo[FrameT: BaseConversionFrame]:
    field_info: FieldInfo
    frame: FrameT


@dataclass
class ValidationInfo(BaseConversionInfo[ValidationFrame]):
    """
    Info which can be optionally passed to validator method.
    """


@dataclass
class SerializationInfo(BaseConversionInfo[SerializationFrame]):
    """
    Info which can be optionally passed to serializer method.
    """


class BaseFieldRegistrationInfo[RawFuncT: Callable, BoundFuncT: Callable]:

    attr_name: str
    """
    Name of the attribute used to access this info, set on subclass.
    """

    func: RawFuncT
    """
    Registered function.
    """

    sig: SignatureInfo
    """
    Signature of registered function.
    """

    field_names: tuple[str, ...] | None
    """
    Field names to which this info applies, or `None` to apply to all fields.
    """

    def __init__(self, func: RawFuncT, field_names: tuple[str, ...] | None):
        self.func = func
        self.field_names = field_names
        self.sig = SignatureInfo(func)
        self._post_init()

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(func={self.func}, field_names={self.field_names})"
        )

    @classmethod
    def aggregate_infos(cls, model_cls: type[BaseModel]) -> list[Self]:
        """
        Aggregate all instances of this registration info from this class.
        """
        infos: list[Self] = []

        # check each attribute model class
        for attr in vars(model_cls).values():
            # extract function from classmethod if applicable
            attr = _normalize_attr(attr)

            # skip if not callable
            if not callable(attr):
                continue

            # check for this attribute
            if info := getattr(attr, cls.attr_name, None):
                assert isinstance(info, cls)
                infos.append(info)

        return infos

    def get_bound_func(self, model: BaseModel | type[BaseModel]) -> BoundFuncT:
        """
        Get the registered function as bound to the given object.
        """
        return getattr(model, self.func.__name__)

    def _post_init(self):
        """
        Can be implemented to validate this info and set additional attributes.
        """


class BaseTypeConvertersInfo[
    RawFuncT: Callable, BoundFuncT: Callable, ConverterT: BaseTypeConverter
](BaseFieldRegistrationInfo[RawFuncT, BoundFuncT]):

    @classmethod
    def aggregate_converters(
        cls, model_cls: type[BaseModel], infos: tuple[Self, ...]
    ) -> tuple[ConverterT, ...]:
        """
        Aggregate converters from infos by calling each function.
        """
        converters: list[ConverterT] = []
        for info in infos:
            converters += info.get_bound_func(model_cls)()
        return tuple(converters)


class TypeValidatorsInfo(
    BaseTypeConvertersInfo[
        TypeValidatorsFuncType, BoundTypeValidatorsFuncType, BaseTypeValidator
    ]
):
    """
    Stores info about a method decorated with `@type_validators` which returns a tuple
    of validators.
    """

    attr_name = TYPED_VALIDATORS_ATTR


class TypeSerializersInfo(
    BaseTypeConvertersInfo[
        TypeSerializersFuncType, BoundTypeSerializersFuncType, BaseTypeSerializer
    ]
):
    """
    Stores info about a method decorated with `@type_serializers` which returns a tuple
    of serializers.
    """

    attr_name = TYPED_SERIALIZERS_ATTR


class BaseFieldConverterInfo[RawFuncT: Callable, BoundFuncT: Callable](
    BaseFieldRegistrationInfo[RawFuncT, BoundFuncT]
):
    """
    Common info for field validator/serializer.
    """

    takes_info: bool

    def _post_init(self):
        args = self.sig.get_params(positional=True)
        if not len(args) in {2, 3}:
            raise TypeError(
                "Function {} has unexpected number of args, must be 2 or 3: got {}".format(
                    self.func, len(args)
                )
            )
        self.takes_info = len(args) == 3


class FieldValidatorInfo(
    BaseFieldConverterInfo[FieldValidatorFuncType, BoundFieldValidatorFuncType]
):
    """
    Stores info about a method decorated with `@field_validator`.
    """

    attr_name = FIELD_VALIDATOR_ATTR

    mode: ValidatorModeType
    """
    Validator mode.
    """

    def __init__(
        self,
        func: FieldValidatorFuncType,
        field_names: tuple[str, ...] | None,
        mode: ValidatorModeType,
    ):
        super().__init__(func, field_names)
        self.mode = mode


class FieldSerializerInfo(
    BaseFieldConverterInfo[FieldSerializerFuncType, BoundFieldSerializerFuncType]
):
    """
    Stores info about a method decorated with `@field_serializer`.
    """

    attr_name = FIELD_SERIALIZER_ATTR


@dataclass
class RegistrationInfo:
    """
    Encapsulates validator/serializer registration info.
    """

    # type_validators: list[BaseValidator]
    # type_serializers: list[BaseSerializer]
    type_validators_infos: list[TypeValidatorsInfo]
    type_serializers_infos: list[TypeSerializersInfo]
    field_validator_infos: list[FieldValidatorInfo]
    field_serializer_infos: list[FieldSerializerInfo]

    @classmethod
    def from_model_cls(cls, model_cls: type[BaseModel]) -> RegistrationInfo:
        """
        Get registration info from model class.
        """
        from .base import BaseModel

        type_validators_infos: list[TypeValidatorsInfo] = []
        type_serializers_infos: list[TypeSerializersInfo] = []
        field_validator_infos: list[FieldValidatorInfo] = []
        field_serializer_infos: list[FieldSerializerInfo] = []

        # traverse class hierarchy in reverse MRO order
        for check_cls in reversed(model_cls.mro()):

            # skip non-model classes
            if not issubclass(check_cls, BaseModel):
                continue

            # get infos from class
            type_validators_infos += TypeValidatorsInfo.aggregate_infos(check_cls)
            type_serializers_infos += TypeSerializersInfo.aggregate_infos(check_cls)
            field_validator_infos += FieldValidatorInfo.aggregate_infos(check_cls)
            field_serializer_infos += FieldSerializerInfo.aggregate_infos(check_cls)

        return RegistrationInfo(
            type_validators_infos,
            type_serializers_infos,
            field_validator_infos,
            field_serializer_infos,
        )


@overload
def type_validators[FuncT: TypeValidatorsFuncType](
    func: FuncT,
    /,
) -> FuncT: ...


@overload
def type_validators[FuncT: TypeValidatorsFuncType](
    *field_names: str,
) -> Callable[[FuncT], FuncT]: ...


def type_validators[FuncT: TypeValidatorsFuncType](
    func_or_name: FuncT | str | None = None, *field_names: str
) -> FuncT | Callable[[FuncT], FuncT]:

    # for type checking func is FuncT, but at runtime it should actually be a
    # classmethod descriptor
    def register(
        clsmethod: FuncT | classmethod,
        field_names: tuple[str, ...] | None = None,
    ) -> FuncT:
        assert isinstance(clsmethod, classmethod)
        func = clsmethod.__func__
        info = TypeValidatorsInfo(func, field_names)
        setattr(func, TYPED_VALIDATORS_ATTR, info)
        return cast(FuncT, clsmethod)

    if isinstance(func_or_name, classmethod):
        assert len(field_names) == 0
        return register(func_or_name)

    all_names = (
        (func_or_name, *field_names) if isinstance(func_or_name, str) else field_names
    )
    assert all(isinstance(n, str) for n in all_names)

    def decorator(func: FuncT) -> FuncT:
        return register(func, all_names or None)

    return decorator


@overload
def type_serializers[FuncT: TypeSerializersFuncType](
    func: FuncT,
    /,
) -> FuncT: ...


@overload
def type_serializers[FuncT: TypeSerializersFuncType](
    *field_names: str,
) -> Callable[[FuncT], FuncT]: ...


def type_serializers[FuncT: TypeSerializersFuncType](
    func_or_name: FuncT | str | None = None, *field_names: str
) -> FuncT | Callable[[FuncT], FuncT]:
    """
    Decorator to register a classmethod that returns type-based serializers.
    """

    def register(
        clsmethod: FuncT | classmethod,
        field_names: tuple[str, ...] | None = None,
    ) -> FuncT:
        assert isinstance(clsmethod, classmethod)
        func = clsmethod.__func__
        info = TypeSerializersInfo(func, field_names)
        setattr(func, TYPED_SERIALIZERS_ATTR, info)
        return cast(FuncT, clsmethod)

    if isinstance(func_or_name, classmethod):
        assert len(field_names) == 0
        return register(func_or_name)

    all_names = (
        (func_or_name, *field_names) if isinstance(func_or_name, str) else field_names
    )
    assert all(isinstance(n, str) for n in all_names)

    def decorator(func: FuncT) -> FuncT:
        return register(func, all_names or None)

    return decorator


@overload
def field_validator[FuncT: FieldValidatorFuncType](
    func: FuncT,
    /,
) -> FuncT: ...


@overload
def field_validator[FuncT: FieldValidatorFuncType](
    *field_names: str,
    mode: Literal["before", "after"] = "before",
) -> Callable[[FuncT], FuncT]: ...


def field_validator[FuncT: FieldValidatorFuncType](
    func_or_name: FuncT | str | None = None,
    *names: str,
    mode: ValidatorModeType = "before",
) -> FuncT | Callable[[FuncT], FuncT]:
    """
    Decorator to register a field-level validator.

    If field names are omitted, the validator applies to all fields.
    """

    def register(
        func: FuncT | classmethod,
        field_names: tuple[str, ...] | None = None,
    ) -> FuncT:
        normalized_func = _normalize_attr(func)
        info = FieldValidatorInfo(normalized_func, field_names, mode)
        setattr(normalized_func, FIELD_VALIDATOR_ATTR, info)
        return cast(FuncT, func)

    if isinstance(func_or_name, (Callable, classmethod)):
        assert len(names) == 0
        return register(func_or_name)

    all_names = (func_or_name, *names) if isinstance(func_or_name, str) else names
    assert all(isinstance(n, str) for n in all_names)

    def decorator(func: FuncT) -> FuncT:
        return register(func, all_names or None)

    return decorator


@overload
def field_serializer[T: FieldSerializerFuncType](
    func: T,
    /,
) -> T: ...


@overload
def field_serializer[T: FieldSerializerFuncType](
    *field_names: str,
) -> Callable[[T], T]: ...


def field_serializer[T: FieldSerializerFuncType](
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
        assert len(names) == 0
        return register(func_or_name)

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

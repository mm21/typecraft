from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import (
    Any,
    Callable,
    Self,
    dataclass_transform,
)

from ..converting.converter import MatchSpec
from ..converting.serializer import (
    BaseSerializer,
    SerializationFrame,
    SerializerRegistry,
)
from ..converting.symmetric_converter import BaseSymmetricConverter
from ..converting.validator import BaseValidator, ValidatorRegistry
from ..serializing import SerializationParams
from ..validating import ValidationFrame, ValidationParams
from .fields import (
    FIELD_VALIDATOR_ATTR,
    TYPED_SERIALIZERS_ATTR,
    TYPED_VALIDATORS_ATTR,
    FieldInfo,
    FieldSerializerInfo,
    FieldValidatorInfo,
    TypedSerializersInfo,
    TypedValidatorsInfo,
)

__all__ = [
    "ModelConfig",
    "BaseModel",
]


@dataclass(kw_only=True)
class ModelConfig:
    """
    Configures model.
    """

    validation_params: ValidationParams | None = None
    """
    Params to use for validation.
    """

    serialization_params: SerializationParams | None = None
    """
    Params to use for serialization.
    """

    validate_on_assignment: bool = False
    """
    Validate when attributes are set, not just when the class is created.
    """


@dataclass_transform(kw_only_default=True)
class BaseModel:
    """
    Base class to transform subclass to model and provide recursive field validation.
    """

    model_config: ModelConfig = ModelConfig()
    """
    Set on subclass to configure this model.
    """

    __built: bool = False
    """
    Whether model build has completed for this class.
    """

    __init_done: bool = False
    """
    Whether initialization has completed for this instance.
    """

    __fields: MappingProxyType[str, FieldInfo]
    """
    Mapping of field names to info objects.

    Only set during model build.
    """

    __dataclass_init: Callable[..., None]
    """
    The original `__init__()` created by the dataclass.
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls = dataclass(cls, kw_only=True)

        # swap out newly created init for wrapper
        cls.__dataclass_init = cls.__init__
        cls.__init__ = cls.__init_wrapper

    def __post_init__(self):
        self.__init_done = True

    def __setattr__(self, name: str, value: Any):
        field_info = self.__fields.get(name)

        # validate value if applicable
        if field_info and (
            not self.__init_done or self.model_config.validate_on_assignment
        ):
            obj = self._run_field_validators_before(field_info, value)
            obj = field_info._adapter.validate(obj)
            obj = self._run_field_validators_after(field_info, obj)
        else:
            obj = value

        super().__setattr__(name, obj)

    @property
    def model_fields(self) -> MappingProxyType[str, FieldInfo]:
        """
        Get fields defined on this model.
        """
        return self.__fields

    @classmethod
    def model_build(cls):
        """
        Build this model:

        - Extract type annotations and create model fields
        - Extract decorated validators/serializers
        - Register type-based validators/serializers
        - Register field validators/serializers
        """
        # extract typed validators/serializers from decorated methods
        typed_validators: list[BaseValidator] = []
        typed_serializers: list[BaseSerializer] = []
        field_validators_info: list[FieldValidatorInfo] = []
        field_serializers_info: list[FieldSerializerInfo] = []

        # traverse in reverse MRO order
        for check_cls in reversed(cls.mro()):
            for attr_name in vars(check_cls):
                try:
                    attr = getattr(cls, attr_name)
                except AttributeError:
                    continue

                # check for typed validators
                if typed_validators_info := getattr(attr, TYPED_VALIDATORS_ATTR, None):
                    assert isinstance(typed_validators_info, TypedValidatorsInfo)
                    typed_validators.extend(typed_validators_info.func(cls))

                # check for typed serializers
                elif typed_serializers_info := getattr(
                    attr, TYPED_SERIALIZERS_ATTR, None
                ):
                    assert isinstance(typed_serializers_info, TypedSerializersInfo)
                    typed_serializers.extend(typed_serializers_info.func(cls))

                # check for field validators
                elif field_validator_info := getattr(attr, FIELD_VALIDATOR_ATTR, None):
                    assert isinstance(field_validator_info, FieldValidatorInfo)
                    field_validators_info.append(field_validator_info)

                # check for field serializers
                elif field_serializer_info := getattr(attr, FIELD_VALIDATOR_ATTR, None):
                    assert isinstance(field_serializer_info, FieldSerializerInfo)
                    field_serializers_info.append(field_serializer_info)

        validator_registry = ValidatorRegistry(*typed_validators)
        serializer_registry = SerializerRegistry(*typed_serializers)

        # create fields with their specific validators/serializers
        fields: dict[str, FieldInfo] = {}
        for f in _get_fields(cls):
            # filter field validators/serializers for this field
            field_validators = tuple(
                v
                for v in field_validators_info
                if v.field_names is None or f.name in v.field_names
            )
            field_serializers = tuple(
                s
                for s in field_serializers_info
                if s.field_names is None or f.name in s.field_names
            )

            fields[f.name] = FieldInfo(
                f,
                cls,
                validator_registry=validator_registry,
                serializer_registry=serializer_registry,
                field_validators=field_validators,
                field_serializers=field_serializers,
            )

        cls.__fields = MappingProxyType(fields)
        cls.__built = True

    @classmethod
    def model_load(cls, obj: Mapping[str, Any], /, *, by_alias: bool = False) -> Self:
        """
        Create instance of model from mapping, substituting aliases if `by_alias` is
        `True`.
        """
        cls.__check_build()
        values: dict[str, Any] = {}

        for name, field_info in cls.__fields.items():
            mapping_name = field_info.get_name(by_alias=by_alias)
            if mapping_name in obj:
                values[name] = obj[mapping_name]

        return cls(**values)

    def model_dump(self, *, by_alias: bool = False) -> dict[str, Any]:
        """
        Dump model to dictionary, substituting aliases if `by_alias` is `True`.
        """
        values: dict[str, Any] = {}

        for name, field_info in self.__fields.items():
            obj = getattr(self, name)
            obj = self._run_field_serializers(field_info, obj)
            serialized_obj = field_info._adapter.serialize(obj)
            mapping_name = field_info.get_name(by_alias=by_alias)
            values[mapping_name] = serialized_obj

        return values

    # TODO: get sig and pass value or value + field_info
    def _run_field_validators_before(self, field_info: FieldInfo, value: Any) -> Any:
        """
        Run field validators with mode="before".
        """
        for validator_info in field_info._field_validators:
            if validator_info.mode != "before":
                continue
            if validator_info.field_names is None:
                # applies to all fields, pass field_info
                value = validator_info.func(self, value, field_info)
            else:
                # applies to specific fields
                value = validator_info.func(self, value)
        return value

    def _run_field_validators_after(self, field_info: FieldInfo, value: Any) -> Any:
        """
        Run field validators with mode="after".
        """
        for validator_info in field_info._field_validators:
            if validator_info.mode != "after":
                continue
            if validator_info.field_names is None:
                # applies to all fields, pass field_info
                value = validator_info.func(self, value, field_info)
            else:
                # applies to specific fields
                value = validator_info.func(self, value)
        return value

    def _run_field_serializers(self, field_info: FieldInfo, value: Any) -> Any:
        """
        Run field serializers.
        """
        for serializer_info in field_info._field_serializers:
            if serializer_info.field_names is None:
                # applies to all fields, pass field_info
                value = serializer_info.func(self, value, field_info)
            else:
                # applies to specific fields
                value = serializer_info.func(self, value)
        return value

    @classmethod
    def __check_build(cls):
        """
        Check whether model has been built and build it if not.
        """
        if not cls.__built:
            cls.model_build()

    def __init_wrapper(self, *args, **kwargs):
        """
        Ensure this model has been built before proceeding with init.
        """
        type(self).__check_build()
        self.__dataclass_init(*args, **kwargs)


class ModelConverter(BaseSymmetricConverter[Mapping[str, Any], BaseModel]):
    """
    Converts a mapping to/from a model.
    """

    validation_match_spec = MatchSpec(assignable_from_target=True)

    @classmethod
    def validate(cls, obj: Mapping[str, Any], frame: ValidationFrame) -> BaseModel:
        type_ = frame.target_annotation.concrete_type
        assert issubclass(type_, BaseModel)
        return type_.model_load(obj, by_alias=frame.params.by_alias)

    @classmethod
    def serialize(cls, obj: BaseModel, frame: SerializationFrame) -> dict[str, Any]:
        return obj.model_dump(by_alias=frame.params.by_alias)


def _get_fields(class_or_instance: Any) -> tuple[dataclasses.Field, ...]:
    """
    Wrapper for `dataclasses.fields()` to enable type checking in case type checkers
    aren't aware `class_or_instance` is actually a dataclass.
    """
    return dataclasses.fields(class_or_instance)

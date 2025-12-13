from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import (
    Any,
    Callable,
    Self,
    cast,
    dataclass_transform,
)

from ..converting.converter import MatchSpec
from ..converting.serializer import (
    JsonSerializableType,
    SerializationFrame,
    SerializerRegistry,
)
from ..converting.symmetric_converter import BaseSymmetricConverter
from ..converting.validator import ValidatorRegistry
from ..serializing import SerializationParams
from ..validating import ValidationFrame, ValidationParams
from .fields import FieldInfo
from .methods import (
    RegistrationInfo,
    ValidatorModeType,
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
    Base class which transforms subclass to dataclass and provides recursive field
    validation/serialization.
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
            # TODO: aggregate errors if not self.__init_done
            obj = self.__invoke_validation(value, field_info)
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

        - Extract decorated validators/serializers
        - Register type-based validators/serializers
        - Register field validators/serializers
        - Extract type annotations and create fields
        """
        registration_info = RegistrationInfo.from_model_cls(cls)
        validator_registry = ValidatorRegistry(*registration_info.typed_validators)
        serializer_registry = SerializerRegistry(*registration_info.typed_serializers)

        # create fields with their specific validators/serializers
        fields: dict[str, FieldInfo] = {}

        for f in _get_fields(cls):
            # filter field validators/serializers for this field
            field_validators = tuple(
                v
                for v in registration_info.field_validators_info
                if v.field_names is None or f.name in v.field_names
            )
            field_serializers = tuple(
                s
                for s in registration_info.field_serializers_info
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

    # TODO: arg: context (optional)
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

    # TODO: model_nested_load()
    # - takes obj, frame
    # - used by symmetric converter

    def model_dump(self, *, by_alias: bool = False) -> dict[str, JsonSerializableType]:
        """
        Dump model to dictionary of JSON-serializable types, substituting aliases if
        `by_alias` is `True`.
        """
        values: dict[str, JsonSerializableType] = {}

        for name, field_info in self.__fields.items():
            obj = getattr(self, name)
            serialized_obj = self.__invoke_serialization(obj, field_info)
            mapping_name = field_info.get_name(by_alias=by_alias)
            values[mapping_name] = serialized_obj

        return values

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

    def __invoke_validation(self, obj: Any, field_info: FieldInfo) -> Any:
        """
        Invoke validation procedure:

        1. Field validators with `mode="before"`
        2. Type-based validators
        3. Field validators with `mode="after"`
        """
        validated_obj = self.__run_field_validators(obj, field_info, mode="before")
        validated_obj = field_info._adapter.validate(validated_obj)
        validated_obj = self.__run_field_validators(
            validated_obj, field_info, mode="after"
        )
        return validated_obj

    def __invoke_serialization(
        self, obj: Any, field_info: FieldInfo
    ) -> JsonSerializableType:
        """
        Invoke serialization procedure:
        1. Field serializers
        2. Type-based serializers
        """
        serialized_obj = self.__run_field_serializers(obj, field_info)
        serialized_obj = field_info._adapter.serialize(serialized_obj)
        return serialized_obj

    def __run_field_validators(
        self, obj: Any, field_info: FieldInfo, *, mode: ValidatorModeType
    ):
        """
        Run field validators with given mode.
        """
        validated_obj = obj
        for validator_info in field_info._get_validators(mode=mode):
            args = list(validator_info.sig.get_params(positional=True))
            assert len(args) in {2, 3}

            self_or_cls = type(self) if validator_info.is_classmethod else self

            if len(args) == 2:
                func = cast(
                    Callable[[BaseModel | type[BaseModel], Any], Any],
                    validator_info.func,
                )
                validated_obj = func(self_or_cls, validated_obj)
            else:
                func = cast(
                    Callable[[BaseModel | type[BaseModel], Any, FieldInfo], Any],
                    validator_info.func,
                )
                validated_obj = func(self_or_cls, validated_obj, field_info)

        return validated_obj

    def __run_field_serializers(self, obj: Any, field_info: FieldInfo) -> Any:
        """
        Run field serializers.
        """
        serialized_obj = obj
        for serializer_info in field_info._field_serializers:
            args = list(serializer_info.sig.get_params(positional=True))
            assert len(args) in {2, 3}

            if len(args) == 1:
                func = cast(Callable[[BaseModel, Any], Any], serializer_info.func)
                serialized_obj = func(self, serialized_obj)
            else:
                func = cast(
                    Callable[[BaseModel, Any, FieldInfo], Any], serializer_info.func
                )
                serialized_obj = func(self, serialized_obj, field_info)

        return serialized_obj


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

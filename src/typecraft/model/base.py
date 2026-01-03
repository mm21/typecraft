from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import MISSING, dataclass
from types import MappingProxyType
from typing import (
    Any,
    Callable,
    Literal,
    Self,
    cast,
    dataclass_transform,
)

from ..converting._types import ERROR_SENTINEL
from ..converting.converter.base import BaseConversionFrame
from ..converting.converter.symmetric import BaseSymmetricTypeConverter
from ..converting.converter.type import MatchSpec
from ..converting.serializer import (
    JSON_SERIALIZABLE_ANNOTATION,
    JsonSerializableType,
    SerializationFrame,
)
from ..exceptions import (
    ConversionErrorDetail,
    ExtraFieldError,
    MissingFieldError,
    SerializationError,
    ValidationError,
)
from ..inspecting.annotations import ANY, Annotation
from ..serializing import SerializationParams
from ..validating import ValidationFrame, ValidationParams
from .fields import FieldInfo
from .methods import (
    BaseConversionInfo,
    BaseFieldConverterInfo,
    RegistrationInfo,
    SerializationInfo,
    ValidationInfo,
    ValidatorModeType,
)

__all__ = [
    "ModelConfig",
    "BaseModel",
]

type ExtraHandlingType = Literal["ignore", "forbid"]
"""
Behaviors with which to handle extra fields.
"""


@dataclass(kw_only=True)
class ModelConfig:
    """
    Configures model.
    """

    validate_on_assignment: bool = False
    """
    Validate when attributes are set, not just when the class is created.
    """

    extra: ExtraHandlingType = "ignore"
    """
    How to handle extra fields not present in model:

    - `"ignore"`: Ignore extra fields
    - `"forbid"`: Raise error upon extra fields
    """

    default_validation_params: ValidationParams | None = None
    """
    Params to use for validation.
    """

    default_serialization_params: SerializationParams | None = None
    """
    Params to use for serialization.
    """


@dataclass_transform(kw_only_default=True)
class BaseModel:
    """
    Base class which transforms subclass to dataclass and provides recursive field
    validation/serialization.
    """

    model_config: ModelConfig | None = None
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

    __model_config: ModelConfig
    """
    Config from user or default.
    """

    __validation_params: ValidationParams
    """
    Validation params passed in `model_validate()`, or defaults.
    """

    __validation_context: Any
    """
    Validation context passed in `model_validate()`, or defaults.
    """

    __validation_errors: list[ConversionErrorDetail]
    """
    Validation errors encountered while constructing model.
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

        # reset built state in case a parent model was already built
        cls.__built = False

        cls = dataclass(cls, kw_only=True)

        # swap out newly created init for wrapper
        cls.__dataclass_init = cls.__init__
        cls.__init__ = cls.__init_wrapper

    def __setattr__(self, name: str, value: Any):
        field_info = self.__fields.get(name)

        # validate value if applicable
        if field_info and (
            not self.__init_done or self.__model_config.validate_on_assignment
        ):
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

        # create fields with their specific validators/serializers
        fields: dict[str, FieldInfo] = {}

        for f in _get_fields(cls):
            type_validators_infos = tuple(
                i
                for i in registration_info.type_validators_infos
                if i.field_names is None or f.name in i.field_names
            )

            type_serializers_infos = tuple(
                i
                for i in registration_info.type_serializers_infos
                if i.field_names is None or f.name in i.field_names
            )

            field_validator_infos = tuple(
                i
                for i in registration_info.field_validator_infos
                if i.field_names is None or f.name in i.field_names
            )
            field_serializer_infos = tuple(
                i
                for i in registration_info.field_serializer_infos
                if i.field_names is None or f.name in i.field_names
            )

            fields[f.name] = FieldInfo(
                f,
                cls,
                type_validators_infos=type_validators_infos,
                type_serializers_infos=type_serializers_infos,
                field_validator_infos=field_validator_infos,
                field_serializer_infos=field_serializer_infos,
            )

        cls.__model_config = cls.model_config or ModelConfig()
        cls.__fields = MappingProxyType(fields)
        cls.__built = True

    @classmethod
    def model_validate(
        cls,
        obj: Mapping[str, Any],
        /,
        *,
        params: ValidationParams | None = None,
        context: Any | None = None,
    ) -> Self:
        """
        Create instance of model from mapping, substituting aliases if `by_alias` is
        `True`.
        """
        cls.__check_build()
        params_ = (
            params or cls.__model_config.default_validation_params or ValidationParams()
        )

        # create a copy of the mapping values
        values = dict(obj)
        values["__validation_params"] = params
        values["__validation_context"] = context

        # convert aliases to field names
        for name, field_info in cls.__fields.items():
            if field_info.metadata.alias:
                mapping_name = field_info.get_name(by_alias=params_.by_alias)
                if mapping_name in values:
                    values[name] = values.pop(mapping_name)

        return cls(**values)

    def model_serialize(
        self, *, params: SerializationParams | None = None, context: Any | None = None
    ) -> dict[str, JsonSerializableType]:
        """
        Dump model to dictionary of JSON-serializable types, substituting aliases if
        `by_alias` is `True`.
        """
        values: dict[str, JsonSerializableType] = {}
        params_ = (
            params
            or self.__model_config.default_serialization_params
            or SerializationParams()
        )

        errors: list[ConversionErrorDetail] = []
        for name, field_info in self.__fields.items():
            obj = getattr(self, name)

            try:
                serialized_obj = self.__invoke_serialization(
                    obj, field_info, params_, context
                )
            except SerializationError as e:
                assert e.errors
                errors += [e._bubble_frame(field_info.name) for e in e.errors]
            else:
                mapping_name = field_info.get_name(by_alias=params_.by_alias)
                values[mapping_name] = serialized_obj

        if errors:
            raise SerializationError(Annotation(type(self)), errors)

        return values

    @classmethod
    def __check_build(cls):
        """
        Check whether model has been built and build it if not.
        """
        if not cls.__built:
            cls.model_build()

    def __init_wrapper(self, **kwargs: Any):
        """
        Perform setup before proceeding with dataclass init.
        """
        type(self).__check_build()

        # get parameters passed from model_validate()
        validation_params = cast(
            ValidationParams | None, kwargs.pop("__validation_params", None)
        )
        validation_context = cast(Any | None, kwargs.pop("__validation_context", None))

        # set params in order of precedence: passed by user -> model config -> default
        self.__validation_params = (
            validation_params
            or self.__model_config.default_validation_params
            or ValidationParams()
        )
        self.__validation_context = validation_context
        self.__validation_errors = []

        # create a new dict if we didn't already create one in model_validate()
        # - then the source data is kept intact
        values = kwargs if validation_params else kwargs.copy()

        # find extra fields
        extra_fields = [k for k in values if k not in self.__fields]

        # delete extra fields before propagating to dataclass's init
        for field_name in extra_fields:
            del values[field_name]

        # fill in missing fields
        required_fields = [
            f
            for f in self.__fields.values()
            if f.field.default is MISSING and f.field.default_factory is MISSING
        ]
        missing_fields = [f for f in required_fields if f.name not in kwargs]
        for f in missing_fields:
            values[f.name] = ERROR_SENTINEL

        # invoke dataclass's init to set attributes from user, aggregating errors
        # since __init_done has not been set yet
        self.__dataclass_init(**values)

        # raise errors if extra fields not allowed
        if self.__model_config.extra == "forbid":
            for field_name in extra_fields:
                frame = ValidationFrame(
                    source_annotation=ANY,
                    target_annotation=ANY,
                    params=self.__validation_params,
                    context=self.__validation_context,
                    path=(field_name,),
                )
                exc = ExtraFieldError()
                self.__validation_errors.append(ConversionErrorDetail(Any, frame, exc))

        # raise errors if required fields not passed
        for f in missing_fields:
            frame = ValidationFrame(
                source_annotation=ANY,
                target_annotation=ANY,
                params=self.__validation_params,
                context=self.__validation_context,
                path=(f.name,),
            )
            exc = MissingFieldError()
            self.__validation_errors.append(ConversionErrorDetail(Any, frame, exc))

        # raise any aggregated validation errors
        if errors := self.__validation_errors:
            raise ValidationError(Annotation(type(self)), errors)

        self.__init_done = True

    def __invoke_validation(self, obj: Any, field_info: FieldInfo) -> Any:
        """
        Invoke validation procedure:

        1. Field validators with `mode="before"`
        2. Type-based validators
        3. Field validators with `mode="after"`
        """
        # pass through error sentinel
        if obj is ERROR_SENTINEL:
            return obj

        frame = field_info._validation_engine.create_frame(
            source_annotation=Annotation(type(obj)),
            target_annotation=field_info.annotation,
            params=self.__validation_params,
            context=self.__validation_context,
        )
        validated_obj = obj

        errors: list[ConversionErrorDetail] = []
        try:
            # invoke "before" validators
            validated_obj = self.__run_field_validators(
                validated_obj, field_info, frame, mode="before"
            )

            # invoke type-based validators
            frame = frame._copy(source_annotation=Annotation(type(validated_obj)))
            validated_obj = field_info._validation_engine.invoke_process(
                validated_obj, frame
            )

            # invoke "after" validators
            frame = frame._copy(source_annotation=Annotation(type(validated_obj)))
            validated_obj = self.__run_field_validators(
                validated_obj, field_info, frame, mode="after"
            )
        except ValidationError as e:
            assert e.errors
            errors += [e._bubble_frame(field_info.name) for e in e.errors]
        except Exception as e:
            errors.append(ConversionErrorDetail(validated_obj, frame, e))

        if errors:
            validated_obj = ERROR_SENTINEL
            if self.__init_done:
                # setting attribute after creating object: raise errors immediately
                raise ValidationError(Annotation(type(self)), errors)
            else:
                # still creating object: aggregate errors; will be raised after all
                # attributes are set
                self.__validation_errors += errors

        return validated_obj

    def __invoke_serialization(
        self,
        obj: Any,
        field_info: FieldInfo,
        params: SerializationParams,
        context: Any | None,
    ) -> JsonSerializableType:
        """
        Invoke serialization procedure:
        1. Field serializers
        2. Type-based serializers
        """
        serialized_obj = obj
        frame = field_info._serialization_engine.create_frame(
            source_annotation=field_info.annotation,
            target_annotation=JSON_SERIALIZABLE_ANNOTATION,
            params=params,
            context=context,
        )

        try:
            serialized_obj = self.__run_field_serializers(
                serialized_obj, field_info, frame
            )
            frame = frame._copy(source_annotation=Annotation(type(serialized_obj)))
            serialized_obj = field_info._serialization_engine.invoke_process(
                serialized_obj, frame
            )
        except SerializationError as e:
            raise e
        except Exception as e:
            raise SerializationError(
                field_info.annotation, [ConversionErrorDetail(serialized_obj, frame, e)]
            )

        return cast(JsonSerializableType, serialized_obj)

    def __run_field_validators(
        self,
        obj: Any,
        field_info: FieldInfo,
        frame: ValidationFrame,
        *,
        mode: ValidatorModeType,
    ):
        """
        Run field validators with given mode.
        """
        return self.__run_field_converters(
            obj,
            field_info,
            frame,
            field_info._get_validator_infos(mode=mode),
            ValidationInfo,
        )

    def __run_field_serializers(
        self, obj: Any, field_info: FieldInfo, frame: SerializationFrame
    ) -> Any:
        """
        Run field serializers.
        """
        return self.__run_field_converters(
            obj,
            field_info,
            frame,
            field_info._get_serializer_infos(),
            SerializationInfo,
        )

    def __run_field_converters[InfoT: BaseConversionInfo](
        self,
        obj: Any,
        field_info: FieldInfo,
        frame: BaseConversionFrame,
        converter_infos: tuple[BaseFieldConverterInfo, ...],
        conversion_info_cls: type[InfoT],
    ):
        """
        Run field converters.
        """
        processed_obj = obj
        for info in converter_infos:
            func = info.get_bound_func(self)
            if info.takes_info:
                info = conversion_info_cls(field_info, frame)
                func = cast(Callable[[Any, InfoT], Any], func)
                processed_obj = func(processed_obj, info)
            else:
                func = cast(Callable[[Any], Any], func)
                processed_obj = func(processed_obj)

        return processed_obj


class ModelConverter(BaseSymmetricTypeConverter[Mapping[str, Any], BaseModel]):
    """
    Converts a mapping to/from a model.
    """

    validation_match_spec = MatchSpec(assignable_from_target=True)

    @classmethod
    def validate(cls, obj: Mapping[str, Any], frame: ValidationFrame) -> BaseModel:
        type_ = frame.target_annotation.concrete_type
        assert issubclass(type_, BaseModel)
        return type_.model_validate(obj, params=frame.params, context=frame.context)

    @classmethod
    def serialize(cls, obj: BaseModel, frame: SerializationFrame) -> dict[str, Any]:
        return obj.model_serialize(params=frame.params, context=frame.context)


def _get_fields(class_or_instance: Any) -> tuple[dataclasses.Field, ...]:
    """
    Wrapper for `dataclasses.fields()` to enable type checking in case type checkers
    aren't aware `class_or_instance` is actually a dataclass.
    """
    return dataclasses.fields(class_or_instance)

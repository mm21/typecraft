"""
Dataclass-based data models with validation.

TODO:
- Decorators to register validators/serializers (model and field level)
    - Remove model_[pre/post]_validate()
- Built-in validation helpers (comparison, range, ...)
- Lambda-based validation (return True if valid)
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import MISSING, dataclass
from types import MappingProxyType
from typing import (
    Any,
    Callable,
    Self,
    dataclass_transform,
    get_type_hints,
    overload,
)

from .adapter import Adapter
from .converting.converter import MatchSpec
from .converting.serializer import (
    BaseSerializer,
    SerializationFrame,
    SerializerRegistry,
)
from .converting.symmetric_converter import BaseSymmetricConverter
from .converting.validator import BaseValidator, ValidatorRegistry
from .inspecting.annotations import Annotation
from .serializing import SerializationParams
from .validating import ValidationFrame, ValidationParams

__all__ = [
    "Field",
    "FieldMetadata",
    "FieldInfo",
    "ModelConfig",
    "BaseModel",
]


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

    # TODO: also take registered validators/serializers for this field
    def __init__(
        self,
        field: dataclasses.Field,
        model_cls: type[BaseModel],
        *,
        validator_registry: ValidatorRegistry,
        serializer_registry: SerializerRegistry,
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
            obj = self.model_pre_validate(field_info, value)
            obj = field_info._adapter.validate(obj)
            obj = self.model_post_validate(field_info, obj)
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
        - Register type-based validators/serializers (invoke classmethods to get
          validator/serializer objects)
        - Register field/model validators/serializers
        """
        # extract typed validators/serializers
        validator_registry = ValidatorRegistry(*cls.model_get_validators())
        serializer_registry = SerializerRegistry(*cls.model_get_serializers())

        # TODO: get registered field validators/serializers and pass to FieldInfo

        # create fields
        cls.__fields = MappingProxyType(
            {
                f.name: FieldInfo(
                    f,
                    cls,
                    validator_registry=validator_registry,
                    serializer_registry=serializer_registry,
                )
                for f in _get_fields(cls)
            }
        )

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
            serialized_obj = field_info._adapter.serialize(obj)
            mapping_name = field_info.get_name(by_alias=by_alias)
            values[mapping_name] = serialized_obj

        return values

    @classmethod
    def model_get_validators(cls) -> tuple[BaseValidator, ...]:
        """
        Override to register type-based validators.
        """
        return tuple()

    @classmethod
    def model_get_serializers(cls) -> tuple[BaseSerializer, ...]:
        """
        Override to register type-based serializers.
        """
        return tuple()

    def model_pre_validate(self, field_info: FieldInfo, value: Any) -> Any:
        """
        Override to perform validation on value before built-in validation.
        """
        _ = field_info
        return value

    def model_post_validate(self, field_info: FieldInfo, value: Any) -> Any:
        """
        Override to perform validation on value after built-in validation.
        """
        _ = field_info
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

"""
Tests for datetime symmetric converters.
"""

from datetime import date, datetime, time

from pytest import raises

from typecraft.adapter import Adapter
from typecraft.converting.builtin_converters import (
    DateConverter,
    DateTimeConverter,
    TimeConverter,
)
from typecraft.converting.serializer import SerializationParams
from typecraft.converting.validator import ValidationParams
from typecraft.exceptions import SerializationError, ValidationError
from typecraft.serializing import TypeSerializerRegistry, serialize
from typecraft.validating import TypeValidatorRegistry, validate


def test_date_converter():
    """
    Test DateConverter for ISO date strings to/from date objects.
    """
    adapter = Adapter(
        date,
        validator_registry=TypeValidatorRegistry(DateConverter.as_validator()),
        serializer_registry=TypeSerializerRegistry(DateConverter.as_serializer()),
    )
    validation_params = ValidationParams(use_builtin_validators=False)
    serialization_params = SerializationParams(use_builtin_serializers=False)

    test_serialized = "2024-03-15"
    test_validated = date(2024, 3, 15)

    # make sure we get an exception without the adapter
    with raises(ValidationError, match="No matching converters"):
        _ = validate(test_serialized, date, params=validation_params)
    with raises(SerializationError, match="No matching converters"):
        _ = serialize(test_validated, params=serialization_params)

    # test validation
    validated = adapter.validate(test_serialized)
    assert isinstance(validated, date)
    assert validated == test_validated

    # test serialization
    serialized = adapter.serialize(test_validated)
    assert isinstance(serialized, str)
    assert serialized == test_serialized

    # test roundtrip with builtin converter
    assert validate(test_serialized, date) == test_validated
    assert serialize(test_validated) == test_serialized

    # test invalid date string
    with raises(ValidationError, match="Invalid isoformat string: 'not-a-date'"):
        _ = adapter.validate("not-a-date")

    with raises(ValidationError, match="month must be in 1..12"):
        _ = adapter.validate("2024-13-45")  # invalid month/day


def test_datetime_converter():
    """
    Test DateTimeConverter for ISO datetime strings to/from datetime objects.
    """
    adapter = Adapter(
        datetime,
        validator_registry=TypeValidatorRegistry(DateTimeConverter.as_validator()),
        serializer_registry=TypeSerializerRegistry(DateTimeConverter.as_serializer()),
    )
    validation_params = ValidationParams(use_builtin_validators=False)
    serialization_params = SerializationParams(use_builtin_serializers=False)

    test_serialized = "2024-03-15T10:30:00"
    test_validated = datetime(2024, 3, 15, 10, 30, 0)

    # make sure we get an exception without the adapter
    with raises(ValidationError, match="No matching converters"):
        _ = validate(test_serialized, datetime, params=validation_params)
    with raises(SerializationError, match="No matching converters"):
        _ = serialize(test_validated, params=serialization_params)

    # test validation
    validated = adapter.validate(test_serialized)
    assert isinstance(validated, datetime)
    assert validated == test_validated

    # test serialization
    serialized = adapter.serialize(test_validated)
    assert isinstance(serialized, str)
    assert serialized == test_serialized

    # test roundtrip with builtin converter
    assert validate(test_serialized, datetime) == test_validated
    assert serialize(test_validated) == test_serialized

    # test invalid datetime string
    with raises(ValidationError, match="Invalid isoformat string: 'not-a-datetime'"):
        _ = adapter.validate("not-a-datetime")


def test_time_converter():
    """
    Test TimeConverter for ISO time strings to/from time objects.
    """
    adapter = Adapter(
        time,
        validator_registry=TypeValidatorRegistry(TimeConverter.as_validator()),
        serializer_registry=TypeSerializerRegistry(TimeConverter.as_serializer()),
    )
    validation_params = ValidationParams(use_builtin_validators=False)
    serialization_params = SerializationParams(use_builtin_serializers=False)

    test_serialized = "10:30:00"
    test_validated = time(10, 30, 0)

    # make sure we get an exception without the adapter
    with raises(ValidationError, match="No matching converters"):
        _ = validate(test_serialized, time, params=validation_params)
    with raises(SerializationError, match="No matching converters"):
        _ = serialize(test_validated, params=serialization_params)

    # test validation
    validated = adapter.validate(test_serialized)
    assert isinstance(validated, time)
    assert validated == test_validated

    # test serialization
    serialized = adapter.serialize(test_validated)
    assert isinstance(serialized, str)
    assert serialized == test_serialized

    # test roundtrip with builtin converter
    assert validate(test_serialized, time) == test_validated
    assert serialize(test_validated) == test_serialized

    # test invalid time string
    with raises(ValidationError, match="Invalid isoformat string: 'not-a-time'"):
        _ = adapter.validate("not-a-time")

    with raises(ValidationError, match="hour must be in 0..23"):
        _ = adapter.validate("25:30:00")  # invalid hour

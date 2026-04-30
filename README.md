<p align="center">
  <img src="./assets/logo-light.svg#gh-light-mode-only" alt="Logo" />
  <img src="./assets/logo-dark.svg#gh-dark-mode-only" alt="Logo" />
</p>

# TypeCraft

Annotation-native toolkit for type inspection, validation, and data modeling

[![Python versions](https://img.shields.io/pypi/pyversions/typecraft.svg)](https://pypi.org/project/typecraft)
[![PyPI](https://img.shields.io/pypi/v/typecraft?color=%2334D058&label=pypi%20package)](https://pypi.org/project/typecraft)
[![Tests](./badges/tests.svg?dummy=8484744)]()
[![Coverage](./badges/cov.svg?dummy=8484744)]()
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

- [TypeCraft](#typecraft)
  - [Motivation](#motivation)
  - [Getting started](#getting-started)
  - [Inspecting annotations](#inspecting-annotations)
    - [The `Annotation` container](#the-annotation-container)
    - [Instance and subtype checks](#instance-and-subtype-checks)
    - [Working with `Annotated[]` metadata](#working-with-annotated-metadata)
  - [Validation and serialization](#validation-and-serialization)
    - [`validate()`](#validate)
    - [`serialize()`](#serialize)
    - [Custom type-based converters](#custom-type-based-converters)
    - [Plain and predicate validators](#plain-and-predicate-validators)
    - [Validator library](#validator-library)
    - [Symmetric converters](#symmetric-converters)
    - [`Adapter`: bidirectional convenience](#adapter-bidirectional-convenience)
  - [Models](#models)
    - [Defining a model](#defining-a-model)
    - [Loading and dumping](#loading-and-dumping)
    - [Field validators and serializers](#field-validators-and-serializers)
    - [Type-based validators and serializers](#type-based-validators-and-serializers)
    - [Aliases](#aliases)
    - [Validate on assignment](#validate-on-assignment)
    - [Forbidding extra fields](#forbidding-extra-fields)
  - [TOML extra](#toml-extra)
    - [Documents and tables](#documents-and-tables)
    - [Arrays](#arrays)
    - [Round-tripping](#round-tripping)

## Motivation

Type annotations in Python are an expressive, structured description of data, but most of that information is discarded at runtime. TypeCraft is a toolkit for putting it back to work. It treats annotations as first-class data, providing a small, composable set of layers that build on each other:

1. A typing layer that wraps an annotation into a rich, introspectable container, with `isinstance`-like and `issubclass`-like checks that honor generics, unions, and `Literal[]`.
2. A conversion layer that uses these annotations to drive validation (loose Python objects &rarr; typed Python objects) and serialization (typed Python objects &rarr; JSON-compatible primitives), with a registry of user-defined converters and full support for nested generics.
3. A modeling layer (`BaseModel`) that turns ordinary dataclasses into validated models with field- and type-level converters, aliases, and configurable behavior &mdash; without metaclass shenanigans.
4. A TOML extra that combines the modeling layer with `tomlkit` to give a typed, mutable, round-trippable interface for TOML documents.

Each layer is usable on its own. You can use `Annotation` purely as a typing utility, or `validate()` and `serialize()` as standalone functions, without ever touching `BaseModel` or the TOML extra.

## Getting started

Install using pip:

```bash
pip install typecraft
```

To use the TOML extra:

```bash
pip install typecraft[toml]
```

## Inspecting annotations

The `Annotation` class is the core typing primitive. It wraps any annotation (including aliases, generics, unions, `Literal[]`, `Annotated[]`, and callables) and exposes a uniform interface for inspecting and reasoning about it.

### The `Annotation` container

```python
from typing import Literal
from typecraft import Annotation

# basic types
a = Annotation(int)
assert a.raw is int
assert a.concrete_type is int

# generic types
a = Annotation(list[int])
assert a.origin is list
assert a.concrete_type is list
assert a.arg_annotations[0].raw is int

# unions
a = Annotation(int | str)
assert a.is_union
assert [arg.raw for arg in a.arg_annotations] == [int, str]

# literals
a = Annotation(Literal["a", "b", "c"])
assert a.is_literal
assert a.args == ("a", "b", "c")

# type aliases are unwrapped
type IntList = list[int]
a = Annotation(IntList)
assert a.origin is list
assert a.arg_annotations[0].raw is int
```

`Annotation` instances are cached by identity, which makes recursive type aliases safe to traverse:

```python
type RecursiveAlias = list[RecursiveAlias] | int

a = Annotation(RecursiveAlias)
list_ann, int_ann = a.arg_annotations

# the inner list[RecursiveAlias] is the same Annotation object as `a`
assert list_ann.arg_annotations[0] is a
```

### Instance and subtype checks

The two most common questions about an annotation are "does this object satisfy it?" (an `isinstance`-like check) and "is this annotation narrower than that one?" (an `issubclass`-like check). TypeCraft exposes both, with full awareness of generics, unions, and `Literal[]`:

```python
from typing import Any, Literal
from typecraft import is_instance, is_narrower

# check if an object satisfies an annotation
assert is_instance(1, int | str)
assert is_instance([1, 2, "3"], list[int | str])
assert not is_instance([1, 2, "3"], list[int])
assert is_instance("a", Literal["a", "b", "c"])

# check if one annotation is narrower (more specific) than another
assert is_narrower(int, int | str)
assert is_narrower(list[int], list[int | str])
assert is_narrower(Literal["a"], Literal["a", "b"])

# Any is both the top type and the bottom type
assert is_narrower(int, Any)
assert is_narrower(Any, int)
```

These functions accept either a raw annotation or an `Annotation` instance, so they're equally usable in throwaway checks and in code that already has an `Annotation` in hand.

### Working with `Annotated[]` metadata

`Annotation` automatically splits `Annotated[]` into the underlying type and its extras, exposing both:

```python
from dataclasses import dataclass
from typing import Annotated
from typecraft import Annotation

@dataclass
class Unit:
    name: str

a = Annotation(Annotated[float, Unit("meters"), "positive"])

# the wrapped type
assert a.raw is float
assert a.concrete_type is float

# extras preserved as a tuple in declaration order
units = [e for e in a.extras if isinstance(e, Unit)]
assert units[0].name == "meters"
assert "positive" in a.extras
```

This is the same machinery that the validation and serialization layers use to discover converters declared inline as `Annotated[T, ...]` extras (see below).

## Validation and serialization

The validation and serialization layers are two faces of the same conversion engine. Both walk an annotation, dispatching to type-based converters at each level.

- **Validation** moves loose data (e.g. JSON, kwargs) towards a typed Python representation.
- **Serialization** moves a typed Python representation back to JSON-compatible primitives (`str`, `int`, `float`, `bool`, `None`, `list`, `dict`).

### `validate()`

In strict mode, `validate()` only accepts objects that already match the target annotation; it fails otherwise. With `strict=False`, builtin coercions kick in:

```python
from typing import Annotated
from typecraft import validate
from typecraft.validating import ValidationParams

# strict mode (the default): no conversions
assert validate([1, 2, 3], list[int]) == [1, 2, 3]

# loose mode: builtin coercions
result = validate(["1", "2", 3], list[int], params=ValidationParams(strict=False))
assert result == [1, 2, 3]

# arbitrarily nested generics are walked recursively
result = validate(
    [[("1", "2"), ("3", "4")], [("5", "6")]],
    list[list[list[int]]],
    params=ValidationParams(strict=False),
)
assert result == [[[1, 2], [3, 4]], [[5, 6]]]

# Annotated[] is transparent
result = validate(
    ["1", "2", "3"],
    Annotated[list[int], "positive integers"],
    params=ValidationParams(strict=False),
)
assert result == [1, 2, 3]
```

When validation fails, all errors found in the object tree are aggregated into a single `ValidationError` with a path-aware message:

```python
from typecraft import validate, ValidationError

try:
    validate([1, 2, "3"], list[str | float])
except ValidationError as e:
    print(e)
```

```text
2 validation errors for list[str | float]
[0]=1: int -> str | float: TypeError
  Errors during union member conversion:
    str: No matching converters
    float: No matching converters
[1]=2: int -> str | float: TypeError
  Errors during union member conversion:
    str: No matching converters
    float: No matching converters
```

### `serialize()`

`serialize()` walks an object and produces a JSON-compatible value: `str`, `int`, `float`, `bool`, `None`, or a `list`/`dict` of the same. Builtin types like `tuple`, `set`, `date`, and `datetime` are converted automatically:

```python
import datetime
from typecraft import serialize

assert serialize((1, 2, 3)) == [1, 2, 3]
assert sorted(serialize({1, 2, 3})) == [1, 2, 3]
assert serialize({"a": [1, 2], "b": [3, 4]}) == {"a": [1, 2], "b": [3, 4]}

# datetimes are serialized to ISO-8601 strings
assert serialize(datetime.date(2026, 1, 1)) == "2026-01-01"
```

By default, the source type is inferred from the object. Pass `source_type` to influence dispatch. For example, when a fixed-length `tuple[int, str]` should be matched by a converter declared on that exact type rather than the generic `tuple[Any, ...]`.

### Custom type-based converters

The conversion engine is driven by a registry of converters. A `TypeValidator` is a function (or callable) that converts an object of one type to another, paired with declarative match rules:

```python
from typecraft import validate
from typecraft.validating import TypeValidator

class Celsius:
    degrees: float
    def __init__(self, degrees: float):
        self.degrees = degrees

# convert from float to Celsius
celsius_validator = TypeValidator(float, Celsius, func=lambda d: Celsius(d))

result = validate(20.0, Celsius, celsius_validator)
assert isinstance(result, Celsius)
assert result.degrees == 20.0
```

Converters work just as well on parameterized types:

```python
from typecraft import validate
from typecraft.validating import TypeValidator

# only convert lists of positive ints
positive_validator = TypeValidator(
    list[int],
    list[str],
    func=lambda obj: [str(o) for o in obj],
    predicate_func=lambda obj: all(o > 0 for o in obj),
)

assert validate([1, 2, 3], list[str], positive_validator) == ["1", "2", "3"]
```

Validators can be passed individually to `validate()` or grouped into a `TypeValidatorRegistry` for reuse. The same applies symmetrically to `TypeSerializer` and `TypeSerializerRegistry`.

Converters can also be attached inline using `Annotated[]`:

```python
from typing import Annotated
from typecraft import serialize, validate
from typecraft.validating import TypeValidator
from typecraft.serializing import TypeSerializer

class MyClass:
    val: int
    def __init__(self, val: int):
        self.val = val

MY_CLASS_VALIDATOR = TypeValidator(int, MyClass, func=lambda obj: MyClass(obj))
MY_CLASS_SERIALIZER = TypeSerializer(MyClass, int, func=lambda obj: obj.val)

type MyClassType = Annotated[MyClass, MY_CLASS_VALIDATOR, MY_CLASS_SERIALIZER]

# validation discovers the inline validator
validated = validate([0, 1, 2], list[MyClassType])
assert all(isinstance(o, MyClass) for o in validated)

# serialization discovers the inline serializer
assert serialize(validated, source_type=list[MyClassType]) == [0, 1, 2]
```

### Plain and predicate validators

Two lighter-weight validator forms run at the annotation level itself, without matching based on type:

- `PredicateValidator` accepts the object if a boolean function returns `True`, and raises otherwise.
- `PlainValidator` runs an arbitrary function; its return value replaces the object, and exceptions become validation errors.

```python
from typing import Annotated
from typecraft import validate
from typecraft.validating import PlainValidator, PredicateValidator

# predicate
positive = PredicateValidator(lambda x: x > 0)
assert validate([1, 2, 3], list[Annotated[int, positive]]) == [1, 2, 3]

# transformer (mode="before" runs prior to type-based validation)
def parse_int(val: object) -> int:
    if isinstance(val, str):
        return int(val.strip())
    if isinstance(val, int):
        return val
    raise TypeError(f"cannot parse {type(val).__name__}")

stripped = PlainValidator(parse_int, mode="before")
assert validate(["  1  ", " 2", "3 "], list[Annotated[int, stripped]]) == [1, 2, 3]
```

### Validator library

For common validation tasks, `typecraft.lib` provides ready-made `BaseValidator` subclasses:

```python
from typing import Annotated
from typecraft import validate
from typecraft.lib import EmailValidator, IntValidator, StrValidator

# numeric bounds
type PortType = Annotated[int, IntValidator(gt=0, lt=65536)]
assert validate(8080, PortType) == 8080

# string length bounds
type ShortStrType = Annotated[str, StrValidator(min_len=1, max_len=64)]
assert validate("hello", ShortStrType) == "hello"

# email pattern
type EmailType = Annotated[str, EmailValidator()]
assert validate("user@example.com", EmailType) == "user@example.com"
```

Build your own by subclassing `BaseValidator[T]` and implementing `validate()`.

### Symmetric converters

When validation and serialization are symmetric, `BaseSymmetricTypeConverter` lets you express both in a single class:

```python
from typecraft.converting.converter.symmetric import BaseSymmetricTypeConverter
from typecraft.serializing import SerializationFrame
from typecraft.validating import ValidationFrame

class RangeConverter(BaseSymmetricTypeConverter[list[int], range]):
    """
    `range` <-> `[start, stop, step]` list.
    """

    @classmethod
    def can_validate(cls, obj: list[int]) -> bool:
        return 1 <= len(obj) <= 3

    @classmethod
    def validate(cls, obj: list[int], frame: ValidationFrame) -> range:
        return range(*obj)

    @classmethod
    def serialize(cls, obj: range, frame: SerializationFrame) -> list[int]:
        return [obj.start, obj.stop, obj.step]

# extract the validator/serializer
validator = RangeConverter.as_validator()
serializer = RangeConverter.as_serializer()
```

Type parameters serve as the source/target types for the validator and serializer, so you don't have to repeat them.

### `Adapter`: bidirectional convenience

For ad-hoc validation and serialization of a specific type, `Adapter` packages both directions and an optional pair of registries into a single object:

```python
from typecraft.adapter import Adapter
from typecraft.serializing import TypeSerializerRegistry
from typecraft.validating import TypeValidatorRegistry

adapter = Adapter(
    range,
    validator_registry=TypeValidatorRegistry(RangeConverter.as_validator()),
    serializer_registry=TypeSerializerRegistry(RangeConverter.as_serializer()),
)

assert adapter.validate([0, 10]) == range(0, 10)
assert adapter.serialize(range(10)) == [0, 10, 1]
```

## Models

`BaseModel` brings the conversion machinery onto a class. A model is a regular `@dataclass(kw_only=True)` under the hood &mdash; no custom metaclass &mdash; with field- and type-level validation, serialization, and aliasing layered on top.

### Defining a model

```python
from typecraft import BaseModel, ModelConfig
from typecraft.validating import ValidationParams

class Person(BaseModel):
    name: str
    age: int = 0

class Team(BaseModel):
    # opt into coercion for nested validation
    model_config = ModelConfig(default_validation_params=ValidationParams(strict=False))

    name: str
    members: list[Person]

# nested models can be constructed directly...
team = Team(name="Eng", members=[Person(name="Alice", age=30)])

# ...or from plain dicts, which get validated recursively
team = Team(name="Eng", members=[{"name": "Alice", "age": "30"}])
assert team.members[0].age == 30
```

Validation errors at every level of nesting are aggregated into a single `ValidationError` with a path to each problem.

### Loading and dumping

`model_validate()` builds an instance from a mapping, and `model_serialize()` produces a JSON-compatible dictionary:

```python
data = {"name": "Eng", "members": [{"name": "Alice", "age": 30}]}

team = Team.model_validate(data)
assert team.members[0].name == "Alice"

dump = team.model_serialize()
assert dump == {"name": "Eng", "members": [{"name": "Alice", "age": 30}]}
```

### Field validators and serializers

Use `@field_validator` and `@field_serializer` to attach custom logic to specific fields. Both decorators support a `mode` argument: `"before"` runs prior to type-based conversion, `"after"` runs once the value is the right type.

```python
from typecraft import BaseModel, field_serializer, field_validator

class Account(BaseModel):
    username: str
    tags: set[str]

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, obj: object) -> object:
        return obj.strip().lower() if isinstance(obj, str) else obj

    @field_validator("username", mode="after")
    @classmethod
    def check_length(cls, obj: str) -> str:
        if not (3 <= len(obj) <= 32):
            raise ValueError("username must be 3-32 chars")
        return obj

    @field_serializer("tags")
    def sort_tags(self, obj: set[str]) -> list[str]:
        return sorted(obj)

acct = Account(username="  Alice  ", tags={"admin", "active"})
assert acct.username == "alice"
assert acct.model_serialize() == {"username": "alice", "tags": ["active", "admin"]}
```

Omit field names to apply the validator/serializer to every field. Validators may take an optional `ValidationInfo` parameter to access the `FieldInfo`, the validation frame, and any user-defined `context`:

```python
from typecraft import BaseModel, field_validator, validate
from typecraft.model.methods import ValidationInfo

class Offset(BaseModel):
    value: int

    @field_validator
    def shift(self, obj: object, info: ValidationInfo) -> object:
        if isinstance(obj, int) and info.frame.context is not None:
            return obj + info.frame.context
        return obj

# context is propagated through validate()
offset = validate({"value": 10}, Offset, context=5)
assert offset.value == 15
```

### Type-based validators and serializers

To attach `TypeValidator`s or `TypeSerializer`s scoped to a model (or a subset of its fields), use `@type_validators` / `@type_serializers`:

```python
from typing import Any
from typecraft import BaseModel, type_serializers, type_validators
from typecraft.validating import TypeValidator
from typecraft.serializing import TypeSerializer

class MyInt(int):
    pass

class Container(BaseModel):
    raw: int
    custom: MyInt

    @type_validators("custom")
    @classmethod
    def validators(cls) -> tuple[TypeValidator[Any, Any], ...]:
        return (TypeValidator(int, MyInt, func=lambda obj: MyInt(obj)),)

    @type_serializers
    @classmethod
    def serializers(cls) -> tuple[TypeSerializer[Any, Any], ...]:
        return (TypeSerializer(MyInt, int, func=lambda obj: int(obj)),)

c = Container(raw=1, custom=2)
assert isinstance(c.custom, MyInt)
assert c.model_serialize() == {"raw": 1, "custom": 2}
```

Pass field names to scope a converter to specific fields, or omit them to apply it to all fields.

### Aliases

`Field(alias=...)` lets a model use a Pythonic field name internally while reading and writing a different key in serialized form. Pass `by_alias=True` to opt into the alias for either direction:

```python
from typecraft import BaseModel, Field
from typecraft.validating import ValidationParams
from typecraft.serializing import SerializationParams

class Config(BaseModel):
    api_key: str = Field(alias="api-key")

# load using the alias
cfg = Config.model_validate({"api-key": "secret"}, params=ValidationParams(by_alias=True))
assert cfg.api_key == "secret"

# dump using the alias
dump = cfg.model_serialize(params=SerializationParams(by_alias=True))
assert dump == {"api-key": "secret"}
```

### Validate on assignment

By default, validation runs only at construction time. Set `validate_on_assignment=True` to revalidate on every attribute assignment:

```python
from typecraft import BaseModel, ModelConfig, ValidationError

class Strict(BaseModel):
    model_config = ModelConfig(validate_on_assignment=True)

    count: int = 0

s = Strict()
s.count = 5

try:
    s.count = "5"  # type: ignore
except ValidationError:
    pass
```

### Forbidding extra fields

By default, extra fields passed to a model are silently ignored. Set `extra="forbid"` to raise on them:

```python
from typecraft import BaseModel, ModelConfig, ValidationError

class Strict(BaseModel):
    model_config = ModelConfig(extra="forbid")

    name: str

try:
    Strict.model_validate({"name": "alice", "rogue": True})
except ValidationError as e:
    print(e)
```

## TOML extra

The `typecraft.extras.toml` module layers TypeCraft's modeling on top of [`tomlkit`](https://github.com/python-poetry/tomlkit) to provide a typed, mutable, round-trippable interface for TOML documents. Field assignments are propagated to the underlying `tomlkit` tree, so item-level details like array multiline-ness, comments, and key ordering are preserved when the document is dumped.

### Documents and tables

Subclass `BaseDocument` for the top-level document and `BaseTable` / `BaseInlineTable` for nested tables. Field types may be Python primitives, `tomlkit` item types, or other wrapper subclasses:

```python
from tomlkit.items import Integer, String
from typecraft import Field
from typecraft.extras.toml import BaseDocument, BaseInlineTable, BaseTable

class ServerTable(BaseTable):
    host: String
    port: Integer

class CredentialsInline(BaseInlineTable):
    user: str
    password: str

class Config(BaseDocument):
    name: String
    server: ServerTable = Field(alias="server")
    credentials: CredentialsInline
    optional_note: str | None = None
```

### Arrays

Use `ArrayWrapper[T]` for arrays of primitive or inline-table items, and `AoTWrapper[T]` for arrays of standalone tables:

```python
from typecraft.extras.toml import AoTWrapper, ArrayWrapper, BaseDocument, BaseTable
from tomlkit.items import String

class Endpoint(BaseTable):
    path: String
    method: String

class API(BaseDocument):
    allowed_ports: ArrayWrapper[int]
    grid: ArrayWrapper[ArrayWrapper[int]]
    endpoints: AoTWrapper[Endpoint]
```

The wrappers behave like ordinary `MutableSequence`s &mdash; iterate, index, append, slice-assign, and so on. Mutations propagate to the underlying `tomlkit` array.

### Round-tripping

Loading parses with `tomlkit` and validates the result against your model. Dumping emits the wrapped `tomlkit` document, so any formatting that came in is preserved on the way out:

```python
from pathlib import Path

config = Config.loads("""\
name = "my-service"
credentials = {user = "admin", password = "hunter2"}

[server]
host = "0.0.0.0"
port = 8080
""")

assert config.server.port == 8080

# mutate freely; the underlying tomlkit document tracks changes
config.server.port = 9090
config.optional_note = "patched"

# dump preserves the original structure plus our edits
print(config.dumps())

# or write straight to a file
config.dump(Path("config.toml"))
```

Setting an `Optional` field to `None` removes the corresponding key from the document, and assigning a wrapper instance plugs it into the same `tomlkit` tree:

```python
new_server = ServerTable(host="127.0.0.1", port=8000)
config.server = new_server

# the new table is now part of the same document
assert config.tomlkit_obj["server"]["port"] == 8000

config.optional_note = None
assert "optional_note" not in config.tomlkit_obj
```

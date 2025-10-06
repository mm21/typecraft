# ModelingKit

Toolkit for data modeling, validation, and typing

Facilitates the following:

- **Data models**: Lightweight, pydantic-like modeling with validation
    - Based on dataclasses, not custom metaclasses; avoids metaclass conflicts
- **Validation**: Mechanism to validate and convert objects based on annotations, with user-defined source/destination types and conversion logic
- **Typing**: Utilities to extract metadata from `Annotated[]`, handle `Literal[]` and unions, and wrap type info in a user-friendly container
- **TOML models**: Wrapper for `tomlkit` with user-defined model classes for documents and tables, also handling arrays of models

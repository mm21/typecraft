# TypeCraft

Annotation-native toolkit for data validation, transformation, and type inspection

Facilitates the following:

- **Validation and transformation**: Mechanism to validate and convert objects based on annotations, with user-defined source/destination types and conversion logic
- **Typing**: Utilities to extract metadata from `Annotated[]`, handle `Literal[]` and unions, and wrap type info in a user-friendly container
- **Data modeling**: Lightweight, pydantic-like modeling with validation
    - Based on dataclasses, avoiding metaclass conflicts
- **TOML modeling**: Wrapper for `tomlkit` with user-defined model classes for documents, tables, and arrays

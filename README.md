# TypeCraft

Annotation-native toolkit for data validation, transformation, and type inspection

[![Python versions](https://img.shields.io/pypi/pyversions/typecraft.svg)](https://pypi.org/project/typecraft)
[![PyPI](https://img.shields.io/pypi/v/typecraft?color=%2334D058&label=pypi%20package)](https://pypi.org/project/typecraft)
[![Tests](./badges/tests.svg?dummy=8484744)]()
[![Coverage](./badges/cov.svg?dummy=8484744)]()
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Facilitates the following:

- **Validation and transformation**: Mechanism to validate and convert objects based on annotations, with user-defined source/destination types and conversion logic
- **Typing**: Utilities to extract metadata from `Annotated[]`, handle `Literal[]` and unions, and wrap type info in a user-friendly container
- **Data modeling**: Lightweight, pydantic-like modeling with validation
    - Based on dataclasses, avoiding metaclass conflicts
- **TOML modeling**: Wrapper for `tomlkit` with user-defined model classes for documents, tables, and arrays

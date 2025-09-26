from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

import tomlkit
from tomlkit.items import Array, InlineTable, Integer, String

from packagekit.modeling.toml import (
    ArrayWrapper,
    BaseDocumentWrapper,
    BaseInlineTableWrapper,
    BaseTableWrapper,
    TableArrayWrapper,
)


@dataclass
class DocumentTest(BaseDocumentWrapper):
    string_test: String
    int_test: Integer
    inline_table_test: InlineTableTest

    array_test: ArrayWrapper[int]
    nested_array_test: ArrayWrapper[ArrayWrapper[int]]
    inline_table_array_test: ArrayWrapper[InlineTableTest]

    table_test: Annotated[TableTest, "table-test"]
    table_array_test: TableArrayWrapper[TableTest]


@dataclass
class TableTest(BaseTableWrapper):
    table_string_test: String


@dataclass
class InlineTableTest(BaseInlineTableWrapper):
    inline_table_string_test: str
    inline_table_int_test: int


DOCUMENT_STR = """
string_test = "test string"
int_test = 123
inline_table_test = {inline_table_string_test = "abc", inline_table_int_test = 123}
array_test = [1, 2, 3]
nested_array_test = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
inline_table_array_test = [
    {inline_table_string_test = "def", inline_table_int_test = 1},
    {inline_table_string_test = "ghi", inline_table_int_test = 2},
]

[table-test]
table_string_test = "table test string"

[[table_array_test]]
table_string_test = "table array test string 1"

[[table_array_test]]
table_string_test = "table array test string 2"
"""


def test_document():
    document = DocumentTest.loads(DOCUMENT_STR)

    assert document.string_test == "test string"

    assert document.int_test == 123

    assert document.inline_table_test.inline_table_string_test == "abc"
    assert document.inline_table_test.inline_table_int_test == 123

    assert document.array_test == [1, 2, 3]

    assert document.nested_array_test == [[1, 2, 3], [4, 5, 6], [7, 8, 9]]

    assert len(document.inline_table_array_test) == 2
    it1, it2 = document.inline_table_array_test
    assert it1.inline_table_string_test == "def"
    assert it1.inline_table_int_test == 1
    assert it2.inline_table_string_test == "ghi"
    assert it2.inline_table_int_test == 2

    assert document.table_test.table_string_test == "table test string"

    assert len(document.table_array_test) == 2
    for i, table in enumerate(document.table_array_test):
        assert isinstance(table, TableTest)
        assert table.table_string_test == f"table array test string {i+1}"

    # modify and read back

    document.array_test[0] = 10
    assert isinstance(document.array_test[0], Integer)
    assert document.array_test == [10, 2, 3]

    new_inner_array = ArrayWrapper([10])
    assert isinstance(new_inner_array.tomlkit_obj, Array)

    # has already been converted to tomlkit obj
    assert isinstance(new_inner_array[0], Integer)
    new_inner_array.append(20)
    assert isinstance(new_inner_array[1], Integer)
    document.nested_array_test[0] = new_inner_array
    assert document.nested_array_test[0] == [10, 20]

    new_inline_table = InlineTableTest(
        inline_table_string_test="jkl", inline_table_int_test=3
    )
    assert isinstance(new_inline_table.inline_table_string_test, String)
    assert isinstance(new_inline_table.inline_table_int_test, Integer)
    document.inline_table_array_test.append(new_inline_table)
    assert len(document.inline_table_array_test) == 3
    inline_table_array_test = document.tomlkit_obj["inline_table_array_test"]
    assert isinstance(inline_table_array_test, Array)
    assert len(inline_table_array_test) == 3
    assert all(isinstance(i, InlineTable) for i in inline_table_array_test)

    document.table_test = TableTest(
        table_string_test=tomlkit.string("table test string 2")
    )
    assert document.table_test.table_string_test == "table test string 2"
    assert isinstance(document.table_test.table_string_test, String)
    assert document.tomlkit_obj["table-test"]["table_string_test"] == "table test string 2"  # type: ignore
    assert document.table_test.table_string_test is document.tomlkit_obj["table-test"]["table_string_test"]  # type: ignore

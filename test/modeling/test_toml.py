from __future__ import annotations

import tomlkit
from tomlkit.items import Integer, String

from packagekit.modeling.toml import (
    Array,
    BaseDocument,
    BaseInlineTable,
    BaseTable,
    TableArray,
)


class DocumentTest(BaseDocument):
    string_test: String
    int_test: Integer
    inline_table_test: InlineTableTest

    array_test: Array[Integer]
    nested_array_test: Array[Array[Integer]]
    # TODO: array of inline tables

    table_test: TableTest
    table_array_test: TableArray[TableTest]


class TableTest(BaseTable):
    table_string_test: String


class InlineTableTest(BaseInlineTable):
    inline_table_string_test: String
    inline_table_int_test: Integer


DOCUMENT_STR = """
string_test = "test string"
int_test = 123
inline_table_test = {inline_table_string_test = "abc", inline_table_int_test = 123}
array_test = [1, 2, 3]
nested_array_test = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]

[table_test]
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

    assert document.table_test.table_string_test == "table test string"

    assert len(document.table_array_test) == 2
    for i, table in enumerate(document.table_array_test):
        assert isinstance(table, TableTest)
        assert table.table_string_test == f"table array test string {i+1}"

    # modify and read back

    document.array_test[0] = tomlkit.integer(10)
    assert document.array_test == [10, 2, 3]

    new_inner_array = Array()
    document.nested_array_test[0] = new_inner_array
    new_inner_array.append(10)
    assert document.nested_array_test[0][0] == 10

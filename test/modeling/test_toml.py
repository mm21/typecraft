from __future__ import annotations

from typing import Annotated

from packagekit.modeling.toml import (
    Array,
    ArrayInfo,
    BaseDocument,
    BaseInlineTable,
    BaseTable,
    TableArray,
)


class DocumentTest(BaseDocument):
    string_test: str
    int_test: int
    inline_table_test: InlineTableTest

    array_test: Array[int]
    multiline_array_test: Annotated[Array[int], ArrayInfo(multiline=True)]
    nested_array_test: Array[Array[int]]
    # TODO: array of inline tables

    table_test: TableTest
    table_array_test: TableArray[TableTest]


class TableTest(BaseTable):
    table_string_test: str


class InlineTableTest(BaseInlineTable):
    inline_table_string_test: str
    inline_table_int_test: int


DOCUMENT_STR = """
string_test = "test string"
int_test = 123
inline_table_test = {inline_table_string_test = "abc", inline_table_int_test = 123}
array_test = [1, 2, 3]
multiline_array_test = [3, 2, 1] # will be converted to multiline upon dumping
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
    assert document.array_test._array_info.multiline is None

    assert document.multiline_array_test == [3, 2, 1]
    assert document.multiline_array_test._array_info.multiline is True

    assert document.nested_array_test == [[1, 2, 3], [4, 5, 6], [7, 8, 9]]

    assert document.table_test.table_string_test == "table test string"

    assert len(document.table_array_test) == 2
    for i, table in enumerate(document.table_array_test):
        assert isinstance(table, TableTest)
        assert table.table_string_test == f"table array test string {i+1}"

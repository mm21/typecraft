from __future__ import annotations

from typing import Annotated

from packagekit.modeling.toml import (
    Array,
    ArrayInfo,
    BaseDocument,
    BaseTable,
    TableArray,
)


class DocumentTest(BaseDocument):
    string_test: str
    int_test: int
    table_test: TableTest
    # TODO: inline table

    # TODO: array of arrays, array of inline tables
    array_test: Array[int]
    multiline_array_test: Annotated[Array[int], ArrayInfo(multiline=True)]
    table_array_test: TableArray[TableTest]


class TableTest(BaseTable):
    table_string_test: str


DOCUMENT_STR = """
string_test = "test string"
int_test = 123
array_test = [1, 2, 3]
multiline_array_test = [3, 2, 1] # will be converted to multiline upon dumping

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
    assert document.array_test == [1, 2, 3]
    assert document.array_test._array_info.multiline is None
    assert document.multiline_array_test == [3, 2, 1]
    assert document.multiline_array_test._array_info.multiline is True
    assert document.table_test.table_string_test == "table test string"

    assert len(document.table_array_test) == 2
    for i, table in enumerate(document.table_array_test):
        assert isinstance(table, TableTest)
        assert table.table_string_test == f"table array test string {i+1}"

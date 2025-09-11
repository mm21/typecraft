from __future__ import annotations

from packagekit.modeling.toml import (
    BaseDocument,
    BaseTable,
    PrimitiveArray,
)


class DocumentTest(BaseDocument):
    string_test: str
    int_test: int
    array_test: PrimitiveArray[int]
    table_test: TableTest


class TableTest(BaseTable):
    table_test_str: str


DOCUMENT_STR = """
string_test = "test string"
int_test = 123
array_test = [1, 2, 3]

[table_test]
table_test_str = "table test string"
"""


def test_document():

    document = DocumentTest.loads(DOCUMENT_STR)

    assert document.string_test == "test string"
    assert document.int_test == 123
    assert document.array_test == [1, 2, 3]
    assert document.table_test.table_test_str == "table test string"

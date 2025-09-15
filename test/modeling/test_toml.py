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

    array_test: Array[int]
    nested_array_test: Array[Array[int]]
    inline_table_array_test: Array[InlineTableTest]

    table_test: TableTest
    table_array_test: TableArray[TableTest]


class TableTest(BaseTable):
    table_string_test: String


class InlineTableTest(BaseInlineTable):
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

    new_inner_array = Array([10])
    # hasn't been converted to tomlkit obj yet
    assert isinstance(new_inner_array[0], int)
    document.nested_array_test[0] = new_inner_array
    new_inner_array.append(20)
    # since assigned to a parent, values have been converted to tomlkit objects
    assert isinstance(new_inner_array[0], Integer)
    assert isinstance(new_inner_array[1], Integer)
    assert document.nested_array_test[0] == [10, 20]

    document.inline_table_array_test.append(
        InlineTableTest(inline_table_string_test="jkl", inline_table_int_test=3)
    )
    assert len(document.inline_table_array_test) == 3

    document.table_test = TableTest(
        table_string_test=tomlkit.string("table test string 2")
    )
    assert document.table_test.table_string_test == "table test string 2"
    assert document._tomlkit_obj["table_test"]["table_string_test"] == "table test string 2"  # type: ignore
    assert isinstance(document.table_test.table_string_test, String)

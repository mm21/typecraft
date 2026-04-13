"""
Test validators/serializers passed in `Annotated[]`.
"""

from typing import Annotated

from typecraft.converting.serializer import TypeSerializer
from typecraft.converting.validator import TypeValidator
from typecraft.serializing import serialize
from typecraft.validating import validate


class MyClass:
    val: int

    def __init__(self, val: int):
        self.val = val

    def __eq__(self, other: object) -> bool:
        return other == self.val


MY_CLASS_VALIDATOR = TypeValidator(int, MyClass, func=lambda obj: MyClass(obj))
MY_CLASS_SERIALIZER = TypeSerializer(MyClass, int, func=lambda obj: obj.val)


type MyClassType = Annotated[MyClass, MY_CLASS_VALIDATOR, MY_CLASS_SERIALIZER]

type MyClassListType = list[MyClassType]


def test_annotated():
    """
    Basic test.
    """
    obj = [0, 1, 2]

    # validate
    validated_obj = validate(obj, MyClassListType)
    assert isinstance(validated_obj, list)
    for i in validated_obj:
        assert isinstance(i, MyClass)
    assert validated_obj == obj

    # serialize
    serialized_obj = serialize(validated_obj, source_type=MyClassListType)
    assert isinstance(serialized_obj, list)
    for i in serialized_obj:
        assert isinstance(i, int)
    assert serialized_obj == obj

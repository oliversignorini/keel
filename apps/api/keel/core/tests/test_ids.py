import time
import uuid

from keel.core.ids import uuid7


def test_uuid7_returns_a_uuid() -> None:
    value = uuid7()

    assert isinstance(value, uuid.UUID)


def test_uuid7_sorts_in_creation_order() -> None:
    generated = []
    for _ in range(20):
        generated.append(uuid7())
        time.sleep(0.001)

    assert generated == sorted(generated)


def test_uuid7_values_are_unique() -> None:
    generated = {uuid7() for _ in range(1000)}

    assert len(generated) == 1000

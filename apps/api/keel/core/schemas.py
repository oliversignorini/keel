"""Shared Ninja schema base. Every ``*Out`` schema across the six
apps declared its own ``id: str`` field plus a ``resolve_id`` static
method whose body was always ``return str(obj.id)`` — thirteen identical
copies restating one design decision: UUID primary keys serialize as
strings. ``KeelSchema`` carries both, once."""

from typing import Any

from ninja import Schema


class KeelSchema(Schema):
    id: str

    @staticmethod
    def resolve_id(obj: Any) -> str:
        return str(obj.id)

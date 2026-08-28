"""Shape validation at the edge (PRD §4, "What is the validation
boundary?"). Ninja ``Schema``s replace DRF serializers — Pydantic-native,
no ``Meta`` class indirection.

Three schemas, not one: what a client may send on create, what it may
send on update, and what the API returns. The update schema exists
separately because *unset* has to mean *unchanged* — which is also why
PATCH is the only mutating method on the detail route (see ``views.py``).
"""

# keel:insert schema_imports

from ninja import Schema
from pydantic import Field

from keel.core.schemas import KeelSchema


class __Resource__Out(KeelSchema):
    """What the API returns. Relations are serialized as their id, never
    as a nested object — expanding one is a client decision, and nesting
    it here is how a list endpoint quietly becomes an N+1."""

    # keel:insert out_fields
    created_by: str
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def resolve_created_by(obj: object) -> str:
        return str(obj.created_by_id)  # type: ignore[attr-defined]


class __Resource__In(Schema):
    """Create payload. A required field has no default; an optional one
    defaults to empty rather than to ``None`` so the column never holds
    two different spellings of "nothing"."""

    # keel:insert in_fields


class __Resource__PatchIn(Schema):
    """Update payload — every field optional. ``views.py`` reads it with
    ``exclude_unset=True``, so omitting a field leaves it unchanged and
    sending it as ``null`` is a different request from not sending it."""

    # keel:insert patch_fields

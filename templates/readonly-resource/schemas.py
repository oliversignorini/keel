"""Shape validation at the edge, read-only edition. One schema, not
three: there is no create payload and no update payload because there is
no write path (``gen readonly-resource``).

If this resource later grows a write path, that is `gen resource`, not an
edit here — the write schemas, the services, the audit decorators and the
permission codes arrive together or not at all.

The comment below is a comment and not a docstring, deliberately —
pydantic promotes a schema class's docstring into the generated OpenAPI
document as that component's ``description``, so it is public API surface
rather than a note for the next developer.
"""

# keel:insert schema_imports

from keel.core.schemas import KeelSchema


# What the API returns. Relations are serialized as their id, never as a
# nested object — expanding one is a client decision, and nesting it here
# is how a list endpoint quietly becomes an N+1.
class __Resource__Out(KeelSchema):
    # keel:insert out_fields
    created_by: str
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def resolve_created_by(obj: object) -> str:
        return str(obj.created_by_id)  # type: ignore[attr-defined]

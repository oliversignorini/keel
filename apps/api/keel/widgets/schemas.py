"""Shape validation at the edge (PRD §4, "What is the validation
boundary?"; docs/plans/phase-6.md 6.D). Ninja ``Schema``s replace DRF
serializers — Pydantic-native, no ``Meta`` class indirection."""

from datetime import datetime

from ninja import Schema
from pydantic import Field

from keel.core.schemas import KeelSchema


class WidgetOut(KeelSchema):
    name: str
    description: str
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def resolve_created_by(obj: object) -> str:
        return str(obj.created_by_id)  # type: ignore[attr-defined]


class WidgetIn(Schema):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    status: str = ""


class WidgetPatchIn(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: str | None = None

"""Schema for the audit read surface (PRD §7)."""

from datetime import datetime
from typing import Any

from ninja import Schema

from keel.core.schemas import KeelSchema


class AuditActorOut(Schema):
    id: str
    email: str
    name: str


class AuditLogOut(KeelSchema):
    action: str
    actor: AuditActorOut | None
    impersonator: AuditActorOut | None
    target_type: str
    target_id: str
    metadata: dict[str, Any]
    ip: str | None
    created_at: datetime

    @staticmethod
    def resolve_actor(obj: Any) -> dict[str, Any] | None:
        if obj.actor_id is None:
            return None
        return {"id": str(obj.actor.id), "email": obj.actor.email, "name": obj.actor.name}

    @staticmethod
    def resolve_impersonator(obj: Any) -> dict[str, Any] | None:
        if obj.impersonator_id is None:
            return None
        return {
            "id": str(obj.impersonator.id),
            "email": obj.impersonator.email,
            "name": obj.impersonator.name,
        }

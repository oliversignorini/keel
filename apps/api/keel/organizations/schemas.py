"""Schemas for the organisations/members/roles/invitations API (PRD §7;
phase-10.md 10.C)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from django.utils import timezone
from django.utils.text import slugify
from ninja import Schema
from pydantic import Field, field_validator

from keel.organizations.models import Organization


class UserSummaryOut(Schema):
    id: str
    email: str
    name: str

    @staticmethod
    def resolve_id(obj: Any) -> str:
        return str(obj.id)


class OrganizationOut(Schema):
    id: str
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def resolve_id(obj: Any) -> str:
        return str(obj.id)


class OrganizationCreateIn(Schema):
    name: str = Field(max_length=255)
    slug: str | None = Field(default=None, max_length=255)

    @field_validator("slug")
    @classmethod
    def _slug_not_taken(cls, value: str | None) -> str | None:
        if value and Organization.objects.filter(slug=value).exists():
            raise ValueError("An organisation with this slug already exists.")
        return value


def unique_slug(base: str) -> str:
    base = base or "organisation"
    candidate = base
    suffix = 1
    while Organization.objects.filter(slug=candidate).exists():
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


def resolve_create_slug(payload: OrganizationCreateIn) -> str:
    return payload.slug or unique_slug(slugify(payload.name))


class OrganizationUpdateIn(Schema):
    name: str | None = Field(default=None, max_length=255)


class RoleOut(Schema):
    id: str
    name: str
    permissions: list[str]
    is_preset: bool

    @staticmethod
    def resolve_id(obj: Any) -> str:
        return str(obj.id)


class MembershipOut(Schema):
    id: str
    user: UserSummaryOut
    role: RoleOut
    status: str
    joined_at: datetime | None

    @staticmethod
    def resolve_id(obj: Any) -> str:
        return str(obj.id)


class MembershipRoleUpdateIn(Schema):
    role_id: UUID


class InvitationOut(Schema):
    id: str
    email: str
    role: RoleOut
    invited_by: UserSummaryOut | None
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    status: str
    created_at: datetime

    @staticmethod
    def resolve_id(obj: Any) -> str:
        return str(obj.id)

    @staticmethod
    def resolve_status(obj: Any) -> str:
        if obj.accepted_at is not None:
            return "accepted"
        if obj.revoked_at is not None:
            return "revoked"
        if obj.expires_at <= timezone.now():
            return "expired"
        return "pending"


class InvitationCreateIn(Schema):
    email: str
    role_id: UUID


class TransferIn(Schema):
    membership_id: str

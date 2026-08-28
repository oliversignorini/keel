"""Schemas for the organisations/members/roles/invitations API (PRD §7;
phase-10.md 10.C)."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from django.utils import timezone
from django.utils.text import slugify
from ninja import Schema
from pydantic import Field

from keel.billing.schemas import EntitlementsOut
from keel.organizations.models import Membership, Organization

# api-patterns finding 14: a published vocabulary, not a bare `str` — must
# match Membership.STATUS_CHOICES (keel/organizations/models.py).
MembershipStatus = Literal["active", "suspended"]
assert set(MembershipStatus.__args__) == {choice for choice, _ in Membership.STATUS_CHOICES}  # type: ignore[attr-defined]

# Invitation.status has no model column — it is derived by
# InvitationOut.resolve_status below from three timestamp fields. Published
# here as the enum that derivation actually produces.
InvitationStatus = Literal["pending", "accepted", "revoked", "expired"]


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
    """Shape only (docs/boundary-guardrails.md "Validation boundary"):
    slug uniqueness used to be enforced here via a ``field_validator`` that
    queried ``Organization`` directly — an ORM read outside
    ``selectors.py`` (invariant 1) and a check-then-act race outside the
    service's transaction (the DB could accept a second identical slug
    between this validator running and ``create_organization``'s insert).
    The view now lets the ``slug`` column's own ``unique=True`` constraint
    be the single source of truth and translates the resulting
    ``IntegrityError`` into a 409."""

    name: str = Field(max_length=255)
    slug: str | None = Field(default=None, max_length=255)


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
    status: MembershipStatus
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
    status: InvitationStatus
    created_at: datetime

    @staticmethod
    def resolve_id(obj: Any) -> str:
        return str(obj.id)

    @staticmethod
    def resolve_status(obj: Any) -> InvitationStatus:
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


# --- /me/, /permissions/, /invite/<token>/ response shapes -----------------
# (api-patterns finding 4: these routes previously returned a bare dict, so
# the generated client typed them `void`.)


class MeUserOut(Schema):
    id: str
    email: str
    name: str


class MeOrganizationOut(Schema):
    id: str
    slug: str
    name: str
    role: str | None
    permissions: list[str]
    entitlements: EntitlementsOut


class MeOut(Schema):
    """``GET /api/v1/me/`` — PRD §7: "the single endpoint the client
    renders from." Composes the shapes already resolved by
    ``keel.organizations.views.me`` rather than restating them."""

    user: MeUserOut
    organizations: list[MeOrganizationOut]
    impersonator: MeUserOut | None


class PermissionCodesOut(Schema):
    codes: list[str]
    # api-patterns finding 18: the enumerable set of 403 `code` values a
    # denial can answer with — published alongside the permission codes
    # themselves, same Reference Data Holder, same reasoning.
    denial_reasons: list[str]


class InviteOrganizationOut(Schema):
    name: str
    slug: str


class InviteDetailOut(Schema):
    organization: InviteOrganizationOut
    email: str
    requires_signup: bool

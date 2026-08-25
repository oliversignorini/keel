"""Writes (PRD §4 "Data model"; phase-3.md B.1).

One ``transaction.atomic()`` per service function, opened here and never
in a view. Mutating services are decorated ``@audited`` or
``@not_audited(reason=...)`` (Phase 1's ``keel.core.audit``).

Services may call guards (``keel.organizations.permissions.has_perm``);
they may never reimplement one. A service enforcing a rule authorization
already owns is a second source of truth, and the two will diverge.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.crypto import get_random_string

from keel.billing.entitlements import check_limit
from keel.core.audit import audited
from keel.core.exceptions import Conflict, PermissionDeniedWithReason, UnprocessableEntity
from keel.organizations.models import Invitation, Membership, Organization, Role
from keel.organizations.permissions import Perm, has_perm, is_last_active_owner
from keel.organizations.roles import PRESET_ADMIN, PRESET_OWNER, seed_preset_roles

INVITATION_TOKEN_LENGTH = 48
INVITATION_TTL = timedelta(days=7)


def _sync_stripe_customer(organization_id: Any) -> None:
    """Seam for Stripe customer creation (phase-3.md B.1: "Stripe customer
    creation via ``transaction.on_commit()``, never inline"). Phase 4 owns
    Stripe integration and replaces this body with the real API call;
    until then it is a documented no-op so organisation creation doesn't
    depend on billing being wired up."""


@audited("organization.created")
def create_organization(*, name: str, slug: str, created_by: Any) -> Organization:
    """Atomic: org, Owner membership, three preset roles — all or nothing
    (PRD §8 Phase 3 acceptance)."""
    with transaction.atomic():
        organization = Organization.objects.create(name=name, slug=slug, created_by=created_by)
        preset_roles = seed_preset_roles()
        Membership.objects.create(
            organization=organization,
            user=created_by,
            role=preset_roles[PRESET_OWNER],
            status=Membership.STATUS_ACTIVE,
        )
        transaction.on_commit(lambda: _sync_stripe_customer(organization.id))
    return organization


@audited("organization.updated")
def update_organization(*, organization: Organization, actor: Any, **fields: Any) -> Organization:
    with transaction.atomic():
        for field, value in fields.items():
            setattr(organization, field, value)
        organization.save(update_fields=list(fields))
    return organization


@audited("organization.deleted")
def delete_organization(*, organization: Organization, actor: Any) -> Organization:
    with transaction.atomic():
        organization.deleted_at = timezone.now()
        organization.save(update_fields=["deleted_at"])
    return organization


@audited("organization.ownership_transferred")
def transfer_ownership(
    *,
    organization: Organization,
    from_membership: Membership,
    to_membership: Membership,
    actor: Any,
) -> Membership:
    same_org = (
        to_membership.organization_id == organization.id
        and from_membership.organization_id == organization.id
    )
    if not same_org:
        raise UnprocessableEntity(
            code="membership_not_in_organization",
            message="Both memberships must belong to the organisation being transferred.",
        )
    preset_roles = seed_preset_roles()
    with transaction.atomic():
        to_membership.role = preset_roles[PRESET_OWNER]
        to_membership.save(update_fields=["role"])
        from_membership.role = preset_roles[PRESET_ADMIN]
        from_membership.save(update_fields=["role"])
    return to_membership


def _sync_seats(organization_id: Any) -> None:
    """Dispatches the Tier-1 seat-sync task (docs/plans/phase-4.md B.5).
    Enqueuing rather than calling ``keel.billing.services.sync_seat_quantity``
    directly means a Stripe failure here can never surface as an exception
    from ``accept_invitation``/``remove_member`` — B.5's "membership writes
    succeed while Stripe is unreachable" holds regardless of whether this
    fires from inside a request or a background worker."""
    from keel.billing.tasks import sync_seat_quantity_task

    sync_seat_quantity_task.enqueue(str(organization_id))


def _billing_seat_pricing_enabled() -> bool:
    from django.conf import settings

    return bool(getattr(settings, "BILLING_SEAT_PRICING", False))


@audited("invitation.created")
def create_invitation(
    *, organization: Organization, email: str, role: Role, invited_by: Any
) -> Invitation:
    with transaction.atomic():
        invitation = Invitation.objects.create(
            organization=organization,
            email=email.strip().lower(),
            role=role,
            invited_by=invited_by,
            token=get_random_string(INVITATION_TOKEN_LENGTH),
            expires_at=timezone.now() + INVITATION_TTL,
        )
    return invitation


@audited("invitation.revoked")
def revoke_invitation(*, invitation: Invitation, actor: Any) -> Invitation:
    with transaction.atomic():
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["revoked_at"])
    return invitation


@audited("invitation.accepted")
def accept_invitation(*, invitation: Invitation, user: Any) -> Membership:
    """Atomic: membership created, ``accepted_at`` set (phase-3.md B.1).
    Seat sync fires on commit, behind ``BILLING_SEAT_PRICING``.

    Checked against the plan's seat entitlement before anything is
    written (docs/plans/phase-4.md B.4: "Adding a member beyond the seat
    entitlement returns 402 with upgrade context"). The seat counter only
    counts ``STATUS_ACTIVE`` memberships, so both a brand-new membership
    and reactivating a suspended one genuinely add a seat and are checked;
    re-accepting an already-active membership is a pure no-op and isn't."""
    with transaction.atomic():
        existing = Membership.objects.filter(
            organization=invitation.organization, user=user
        ).first()
        adds_a_new_active_seat = existing is None or existing.status != Membership.STATUS_ACTIVE
        if adds_a_new_active_seat:
            check_limit(invitation.organization, "seats")

        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=["accepted_at"])

        if existing is None:
            membership = Membership.objects.create(
                organization=invitation.organization,
                user=user,
                role=invitation.role,
                status=Membership.STATUS_ACTIVE,
            )
        else:
            membership = existing
            if membership.status != Membership.STATUS_ACTIVE:
                membership.status = Membership.STATUS_ACTIVE
                membership.role = invitation.role
                membership.save(update_fields=["status", "role"])

        if _billing_seat_pricing_enabled():
            transaction.on_commit(lambda: _sync_seats(invitation.organization_id))
    return membership


@audited("membership.role_changed")
def change_member_role(*, membership: Membership, role: Role, actor: Any) -> Membership:
    """The last Owner cannot be demoted (PRD §8 Phase 3 acceptance). Keys
    off ``Perm.ORG_TRANSFER`` — the code only the Owner preset holds — the
    same source of truth ``permissions.is_last_active_owner`` uses for the
    remove-guard, never off a role name."""
    if is_last_active_owner(membership) and Perm.ORG_TRANSFER not in role.permissions:
        raise Conflict(
            code="cannot_demote_last_owner",
            message="The organisation's last owner cannot be demoted.",
            details={"membership_id": str(membership.pk)},
        )
    with transaction.atomic():
        membership.role = role
        membership.save(update_fields=["role"])
    return membership


def expire_invitations() -> int:
    """Invitation expiry (PRD §5 "Scheduled jobs"; docs/plans/phase-5.md
    5.4), hourly. A system action, not a user one — no ``actor``, so not
    ``@audited`` (that decorator records who did it; nobody did this).

    Phase 1's schema has no separate "expired" state on ``Invitation`` —
    only ``accepted_at`` / ``revoked_at``, and no migration is available
    to add one (docs/plans/phase-5.md boundary: "a needed migration
    means a Phase 1 gap"). An invitation past its ``expires_at`` with
    neither set is, in every observable way (it 403s on accept), already
    revoked; this just makes that state visible on the row itself.
    Idempotent by construction: the ``filter`` only ever matches rows
    this hasn't already touched, so a second run updates zero rows."""
    now = timezone.now()
    return Invitation.objects.filter(
        accepted_at__isnull=True, revoked_at__isnull=True, expires_at__lt=now
    ).update(revoked_at=now)


@audited("membership.removed")
def remove_member(*, membership: Membership, actor: Any) -> None:
    """Calls the ``members.remove`` guard with ``membership`` as the
    subject rather than reimplementing the last-owner check — the
    guard, not this function, is authorization's source of truth.

    Seat sync fires on commit, behind ``BILLING_SEAT_PRICING`` — the
    other half of docs/plans/phase-4.md B.5 alongside
    ``accept_invitation``'s ("seat count syncs to Stripe ... on
    membership create and remove")."""
    decision = has_perm(actor, membership.organization, Perm.MEMBERS_REMOVE, subject=membership)
    if not decision.allowed:
        raise PermissionDeniedWithReason(
            code=decision.reason or "permission_denied", details=decision.details
        )
    organization_id = membership.organization_id
    with transaction.atomic():
        membership.delete()
        if _billing_seat_pricing_enabled():
            transaction.on_commit(lambda: _sync_seats(organization_id))

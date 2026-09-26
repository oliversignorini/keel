"""``python manage.py seed_demo`` — a small, idempotent fixture for local
development and demos: one organisation, one verified user per preset
role (``keel.organizations.roles``), and a handful of demo widgets.

Deliberately refuses to run against a non-``DEBUG`` settings module
unless ``--force`` is passed — this creates real rows with a publicly
known password (``DEMO_PASSWORD`` below), which must never land in a
production database by accident.

Idempotent by construction: every row this command creates is looked up
by a stable, deterministic key first (the organisation's slug, each
user's email, each widget's name within the organisation) and only
created if missing, so running it twice leaves the same state as running
it once — no duplicate organisations, users, memberships or widgets, and
no exception on the second run.
"""

from __future__ import annotations

from typing import Any

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from keel.accounts.models import User
from keel.organizations import services
from keel.organizations.models import Membership, Organization
from keel.organizations.roles import (
    PRESET_ADMIN,
    PRESET_MEMBER,
    PRESET_OWNER,
    seed_preset_roles,
)

DEMO_ORG_NAME = "Demo Org"
DEMO_ORG_SLUG = "demo-org"
# Deliberately public: dev-only demo logins, and handle() refuses to run
# unless DEBUG is on (or --force is passed explicitly).
DEMO_PASSWORD = "demo-password-123"  # nosec B105
DEMO_WIDGET_COUNT = 3

# Role name -> local-part of the demo user's email, e.g. "owner@demo.keel.test".
_ROLE_EMAIL_LOCAL_PARTS: dict[str, str] = {
    PRESET_OWNER: "owner",
    PRESET_ADMIN: "admin",
    PRESET_MEMBER: "member",
}
DEMO_EMAIL_DOMAIN = "demo.keel.test"


def _email_for_role(role_name: str) -> str:
    local_part = _ROLE_EMAIL_LOCAL_PARTS[role_name]
    return f"{local_part}@{DEMO_EMAIL_DOMAIN}"


def _get_or_create_verified_user(email: str) -> tuple[User, bool]:
    """Get-or-create the user, then unconditionally ensure a verified,
    primary allauth ``EmailAddress`` exists for it — a user created by an
    earlier, pre-allauth run of this command (or created some other way)
    must still end up loginable without email verification."""
    from allauth.account.models import EmailAddress

    user, created = User.objects.get_or_create(
        email=email,
        defaults={"is_active": True},
    )
    if created:
        user.set_password(DEMO_PASSWORD)
        user.save(update_fields=["password"])

    address, address_created = EmailAddress.objects.get_or_create(
        user=user,
        email=email,
        defaults={"verified": True, "primary": True},
    )
    if not address_created and not (address.verified and address.primary):
        address.verified = True
        address.primary = True
        address.save(update_fields=["verified", "primary"])

    return user, created


def _get_or_create_demo_organization(owner: User) -> tuple[Organization, bool]:
    existing = Organization.objects.filter(slug=DEMO_ORG_SLUG).first()
    if existing is not None:
        return existing, False
    organization = services.create_organization(name=DEMO_ORG_NAME, slug=DEMO_ORG_SLUG, actor=owner)
    return organization, True


def _get_or_create_membership(organization: Organization, user: User, role_name: str) -> bool:
    role = seed_preset_roles()[role_name]
    _membership, created = Membership.objects.get_or_create(
        organization=organization,
        user=user,
        defaults={"role": role, "status": Membership.STATUS_ACTIVE},
    )
    return created


def _seed_demo_widgets(organization: Organization, actor: User) -> int:
    if not apps.is_installed("keel.widgets"):
        return 0

    from keel.widgets.models import Widget
    from keel.widgets.services import create_widget

    created_count = 0
    for index in range(1, DEMO_WIDGET_COUNT + 1):
        name = f"Demo Widget {index}"
        if Widget.objects.filter(organization=organization, name=name).exists():
            continue
        create_widget(
            organization=organization,
            name=name,
            description="Seeded by manage.py seed_demo.",
            status="active",
            actor=actor,
        )
        created_count += 1
    return created_count


class Command(BaseCommand):
    help = (
        "Seed a demo organisation, one verified user per preset role, and a "
        "handful of demo widgets. Idempotent: safe to run repeatedly. "
        "Refuses to run unless DEBUG is true, or --force is passed."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--force",
            action="store_true",
            help="Seed even when DEBUG is false. Never do this against production.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "Refusing to seed demo data: DEBUG is false. Pass --force to override "
                "(never do this against a production database)."
            )

        rows: list[tuple[str, str, str]] = []

        owner_email = _email_for_role(PRESET_OWNER)
        owner, owner_created = _get_or_create_verified_user(owner_email)
        organization, org_created = _get_or_create_demo_organization(owner)
        # create_organization already creates the Owner membership; the
        # get_or_create below is a no-op in that case and covers the case
        # where the organisation already existed but the owner's
        # membership somehow didn't.
        _get_or_create_membership(organization, owner, PRESET_OWNER)
        rows.append((PRESET_OWNER, owner_email, "created" if owner_created else "already existed"))

        for role_name in (PRESET_ADMIN, PRESET_MEMBER):
            email = _email_for_role(role_name)
            user, user_created = _get_or_create_verified_user(email)
            _get_or_create_membership(organization, user, role_name)
            rows.append((role_name, email, "created" if user_created else "already existed"))

        widgets_created = _seed_demo_widgets(organization, owner)

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo organisation: {organization.name} (slug={organization.slug}, "
                f"{'created' if org_created else 'already existed'})"
            )
        )
        self.stdout.write(f"Password for every demo user: {DEMO_PASSWORD}")
        self.stdout.write("")
        self.stdout.write(f"{'ROLE':<8} {'EMAIL':<28} STATUS")
        for role_name, email, status in rows:
            self.stdout.write(f"{role_name:<8} {email:<28} {status}")
        self.stdout.write("")
        if apps.is_installed("keel.widgets"):
            self.stdout.write(f"Demo widgets created this run: {widgets_created}")
        else:
            self.stdout.write("keel.widgets is not installed — skipped demo widgets.")

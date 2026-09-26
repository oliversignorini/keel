"""``manage.py seed_demo`` — idempotent demo fixture (PRD §4 invariant 6's
neighbourly concerns don't apply here; this is a dev-only fixture, not a
production resource, but it still must never touch a live database by
accident and must never leave duplicate rows behind)."""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from keel.accounts.models import User
from keel.organizations.management.commands.seed_demo import DEMO_PASSWORD
from keel.organizations.models import Membership, Organization
from keel.organizations.roles import PRESET_ADMIN, PRESET_MEMBER, PRESET_OWNER
from keel.widgets.models import Widget

pytestmark = pytest.mark.django_db

DEMO_EMAILS = {
    PRESET_OWNER: "owner@demo.keel.test",
    PRESET_ADMIN: "admin@demo.keel.test",
    PRESET_MEMBER: "member@demo.keel.test",
}


def _run(**options: object) -> str:
    out = StringIO()
    call_command("seed_demo", stdout=out, **options)
    return out.getvalue()


def test_refuses_to_run_without_debug_or_force(settings) -> None:
    settings.DEBUG = False

    with pytest.raises(CommandError, match="DEBUG"):
        call_command("seed_demo")

    assert not Organization.objects.filter(slug="demo-org").exists()


def test_force_seeds_even_with_debug_false(settings) -> None:
    settings.DEBUG = False

    _run(force=True)

    assert Organization.objects.filter(slug="demo-org").exists()


def test_seeds_one_verified_primary_email_per_preset_role(settings) -> None:
    from allauth.account.models import EmailAddress

    settings.DEBUG = True

    _run()

    organization = Organization.objects.get(slug="demo-org")
    for role_name, email in DEMO_EMAILS.items():
        user = User.objects.get(email=email)
        assert user.check_password(DEMO_PASSWORD)

        address = EmailAddress.objects.get(user=user, email=email)
        assert address.verified is True
        assert address.primary is True

        membership = Membership.objects.get(organization=organization, user=user)
        assert membership.role.name == role_name
        assert membership.status == Membership.STATUS_ACTIVE


def test_seeds_demo_widgets_owned_by_the_organization(settings) -> None:
    settings.DEBUG = True

    _run()

    organization = Organization.objects.get(slug="demo-org")
    assert Widget.objects.filter(organization=organization).count() >= 1


def test_is_idempotent(settings) -> None:
    settings.DEBUG = True

    _run()

    org_count_after_first = Organization.objects.filter(slug="demo-org").count()
    user_count_after_first = User.objects.filter(email__in=DEMO_EMAILS.values()).count()
    membership_count_after_first = Membership.objects.count()
    widget_count_after_first = Widget.objects.count()

    # Second run must not raise, and must not create any duplicate rows.
    _run()

    assert Organization.objects.filter(slug="demo-org").count() == org_count_after_first == 1
    assert (
        User.objects.filter(email__in=DEMO_EMAILS.values()).count() == user_count_after_first == 3
    )
    assert Membership.objects.count() == membership_count_after_first
    assert Widget.objects.count() == widget_count_after_first


def test_prints_a_summary_with_logins(settings) -> None:
    settings.DEBUG = True

    output = _run()

    assert DEMO_PASSWORD in output
    for email in DEMO_EMAILS.values():
        assert email in output

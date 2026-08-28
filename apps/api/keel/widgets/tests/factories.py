"""Row factory used both by ``WidgetResource.test_factory`` (the
cross-org meta-test walk, CLAUDE.md invariant 6) and directly by this
app's own tests."""

from django.utils.crypto import get_random_string

from keel.accounts.models import User
from keel.organizations.models import Organization
from keel.widgets.models import Widget


def widget_factory(organization: Organization) -> Widget:
    creator = User.objects.create_user(
        email=f"widget-creator-{organization.pk}-{get_random_string(6).lower()}@example.com",
        password="s3cret-pass",
    )
    return Widget.objects.create(
        organization=organization,
        name="A name",
        description="",
        status="",
        created_by=creator,
    )

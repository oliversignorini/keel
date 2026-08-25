import pytest

from keel.accounts.models import User
from keel.organizations.models import Organization
from keel.widgets.models import Widget


@pytest.mark.django_db
def test_for_organization_returns_only_that_organizations_rows() -> None:
    creator = User.objects.create_user(email="ada@example.com", password="s3cret-pass")
    org_a = Organization.objects.create(name="Org A", slug="org-a", created_by=creator)
    org_b = Organization.objects.create(name="Org B", slug="org-b", created_by=creator)
    widget_a = Widget.objects.create(organization=org_a, name="A widget", created_by=creator)
    Widget.objects.create(organization=org_b, name="B widget", created_by=creator)

    result = Widget.objects.for_organization(org_a)

    assert list(result) == [widget_a]

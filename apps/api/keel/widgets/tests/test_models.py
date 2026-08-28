import pytest

from keel.accounts.models import User
from keel.organizations.models import Organization
from keel.widgets.models import Widget
from keel.widgets.tests.factories import widget_factory


@pytest.mark.django_db
def test_for_organization_returns_only_that_organizations_rows() -> None:
    creator = User.objects.create_user(email="ada@example.com", password="s3cret-pass")
    org_a = Organization.objects.create(name="Org A", slug="org-a", created_by=creator)
    org_b = Organization.objects.create(name="Org B", slug="org-b", created_by=creator)
    row_a = widget_factory(org_a)
    widget_factory(org_b)

    result = Widget.objects.for_organization(org_a)

    assert list(result) == [row_a]

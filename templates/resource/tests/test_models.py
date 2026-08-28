import pytest

from keel.__app__.models import __Resource__
from keel.__app__.tests.factories import __resource___factory
from keel.accounts.models import User
from keel.organizations.models import Organization


@pytest.mark.django_db
def test_for_organization_returns_only_that_organizations_rows() -> None:
    creator = User.objects.create_user(email="ada@example.com", password="s3cret-pass")
    org_a = Organization.objects.create(name="Org A", slug="org-a", created_by=creator)
    org_b = Organization.objects.create(name="Org B", slug="org-b", created_by=creator)
    row_a = __resource___factory(org_a)
    __resource___factory(org_b)

    result = __Resource__.objects.for_organization(org_a)

    assert list(result) == [row_a]

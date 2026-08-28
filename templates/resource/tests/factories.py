"""Row factory used both by ``__Resource__Resource.test_factory`` (the
cross-org meta-test walk, CLAUDE.md invariant 6) and directly by this
app's own tests."""

# keel:insert factory_imports
from django.utils.crypto import get_random_string

from keel.__app__.models import __Resource__
from keel.accounts.models import User
from keel.organizations.models import Organization


def __resource___factory(organization: Organization) -> __Resource__:
    creator = User.objects.create_user(
        email=f"__resource__-creator-{organization.pk}-{get_random_string(6).lower()}@example.com",
        password="s3cret-pass",
    )
    return __Resource__.objects.create(
        organization=organization,
        # keel:insert factory_kwargs
        created_by=creator,
    )

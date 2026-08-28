import pytest

from keel.__app__.tasks import notify___resource___created_task
from keel.__app__.tests.factories import __resource___factory
from keel.accounts.models import User
from keel.organizations.models import Organization

pytestmark = pytest.mark.django_db


def test_notify___resource___created_task_runs_synchronously_when_called_directly() -> None:
    creator = User.objects.create_user(email="creator@example.com", password="s3cret-pass")
    org = Organization.objects.create(name="Acme", slug="acme", created_by=creator)
    row = __resource___factory(org)

    notify___resource___created_task(str(row.id))  # does not raise

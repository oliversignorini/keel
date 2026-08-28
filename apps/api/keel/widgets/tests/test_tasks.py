import pytest

from keel.accounts.models import User
from keel.organizations.models import Organization
from keel.widgets.tasks import notify_widget_created_task
from keel.widgets.tests.factories import widget_factory

pytestmark = pytest.mark.django_db


def test_notify_widget_created_task_runs_synchronously_when_called_directly() -> None:
    creator = User.objects.create_user(email="creator@example.com", password="s3cret-pass")
    org = Organization.objects.create(name="Acme", slug="acme", created_by=creator)
    row = widget_factory(org)

    notify_widget_created_task(str(row.id))  # does not raise

"""``python manage.py rotate_connection_tokens``."""

import pytest
from cryptography.fernet import Fernet
from django.core.management import call_command

from keel.accounts.models import User
from keel.connections.models import Connection
from keel.core.crypto import decrypt, encrypt
from keel.organizations.models import Organization

pytestmark = pytest.mark.django_db


def _org() -> tuple[Organization, User]:
    creator = User.objects.create_user(email="creator@example.com", password="s3cret-pass")
    org = Organization.objects.create(name="Acme", slug="acme", created_by=creator)
    return org, creator


def test_command_rotates_rows_and_reports_the_count(settings, capsys) -> None:
    old_key = Fernet.generate_key().decode()
    settings.KEEL_ENCRYPTION_KEYS = [old_key]
    org, user = _org()
    connection = Connection.objects.create(
        organization=org,
        provider="github",
        external_account="acme-bot",
        access_token=encrypt("access-token"),
        refresh_token=encrypt("refresh-token"),
        connected_by=user,
    )

    new_key = Fernet.generate_key().decode()
    settings.KEEL_ENCRYPTION_KEYS = [new_key, old_key]

    call_command("rotate_connection_tokens")

    connection.refresh_from_db()
    assert decrypt(connection.access_token) == "access-token"
    captured = capsys.readouterr()
    assert "Rotated 1 connection" in captured.out
    assert "skipped 0" in captured.out

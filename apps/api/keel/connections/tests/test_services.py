"""``rotate_connection_tokens`` (ddia#27) — the only write ``connections/``
has today. ``connections/`` is otherwise schema-only (no create/update
service), so these tests build ``Connection`` rows directly."""

import pytest
from cryptography.fernet import Fernet

from keel.accounts.models import User
from keel.connections.models import Connection
from keel.connections.services import rotate_connection_tokens
from keel.core.audit import registry as audit_registry
from keel.core.crypto import decrypt, encrypt
from keel.organizations.models import Organization

pytestmark = pytest.mark.django_db


def _org() -> tuple[Organization, User]:
    creator = User.objects.create_user(email="creator@example.com", password="s3cret-pass")
    org = Organization.objects.create(name="Acme", slug="acme", created_by=creator)
    return org, creator


def _connection(org: Organization, user: User, **overrides: object) -> Connection:
    fields: dict = {
        "organization": org,
        "provider": "github",
        "external_account": "acme-bot",
        "access_token": encrypt("access-token-plaintext"),
        "refresh_token": encrypt("refresh-token-plaintext"),
        "connected_by": user,
    }
    fields.update(overrides)
    return Connection.objects.create(**fields)


def test_rotates_both_tokens_onto_the_new_first_key(settings) -> None:
    old_key = Fernet.generate_key().decode()
    settings.KEEL_ENCRYPTION_KEYS = [old_key]
    org, user = _org()
    connection = _connection(org, user)
    original_access = connection.access_token
    original_refresh = connection.refresh_token

    new_key = Fernet.generate_key().decode()
    settings.KEEL_ENCRYPTION_KEYS = [new_key, old_key]

    result = rotate_connection_tokens()

    connection.refresh_from_db()
    assert result == {"rotated": 1, "skipped": 0}
    assert connection.access_token != original_access
    assert connection.refresh_token != original_refresh
    assert decrypt(connection.access_token) == "access-token-plaintext"
    assert decrypt(connection.refresh_token) == "refresh-token-plaintext"

    # Genuinely under the new key alone now — dropping the old key must
    # not break it.
    settings.KEEL_ENCRYPTION_KEYS = [new_key]
    assert decrypt(connection.access_token) == "access-token-plaintext"


def test_skips_a_row_no_configured_key_can_decrypt(settings) -> None:
    settings.KEEL_ENCRYPTION_KEYS = [Fernet.generate_key().decode()]
    org, user = _org()
    connection = _connection(org, user)
    original_access = connection.access_token

    # Simulates a row whose key was dropped from the env var entirely —
    # skip it rather than aborting the whole sweep.
    settings.KEEL_ENCRYPTION_KEYS = [Fernet.generate_key().decode()]

    result = rotate_connection_tokens()

    connection.refresh_from_db()
    assert result == {"rotated": 0, "skipped": 1}
    assert connection.access_token == original_access


def test_rotates_every_row_independently(settings) -> None:
    old_key = Fernet.generate_key().decode()
    settings.KEEL_ENCRYPTION_KEYS = [old_key]
    org, user = _org()
    rotatable = _connection(org, user, provider="github", external_account="a")
    orphaned_key = Fernet.generate_key().decode()
    settings.KEEL_ENCRYPTION_KEYS = [orphaned_key]
    orphaned = _connection(org, user, provider="github", external_account="b")

    new_key = Fernet.generate_key().decode()
    settings.KEEL_ENCRYPTION_KEYS = [new_key, old_key]

    result = rotate_connection_tokens()

    rotatable.refresh_from_db()
    orphaned.refresh_from_db()
    assert result == {"rotated": 1, "skipped": 1}
    assert decrypt(rotatable.access_token) == "access-token-plaintext"


def test_is_audited() -> None:
    """Invariant 7: every mutating service is @audited or @not_audited."""
    entry = audit_registry.get(rotate_connection_tokens)
    assert entry["kind"] == "audited"
    assert entry["action"] == "connections.rotate_encryption_keys"

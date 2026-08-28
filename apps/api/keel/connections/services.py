"""Writes for ``Connection`` (CLAUDE.md's per-app shape: ALL writes live
here). The only write today is the key-rotation sweep (ddia#27) —
``connections/`` is otherwise schema-only, with no create/update/delete
service yet, because nothing in this phase adds the OAuth-connect flow
itself.
"""

from django.db import transaction

from keel.connections.models import Connection
from keel.core.audit import audited
from keel.core.crypto import DecryptionError, rotate


@audited("connections.rotate_encryption_keys")
def rotate_connection_tokens() -> dict[str, int]:
    """Re-encrypts every ``Connection.access_token`` / ``refresh_token``
    under the current first key in ``settings.KEEL_ENCRYPTION_KEYS``
    (``keel.core.crypto.rotate`` — ``MultiFernet.rotate`` under the hood,
    so the plaintext is never exposed to this function).

    One ``transaction.atomic()`` per row (CLAUDE.md invariant 3) rather
    than one for the whole sweep: a table-sized rotation must not hold a
    single long-lived transaction, and a row this function can't rotate
    (``DecryptionError`` — its ciphertext predates every configured key)
    should not abort every row after it.

    Returns ``{"rotated": n, "skipped": n}`` — ``skipped`` is a fact worth
    surfacing to whoever ran the command, not swallowed.
    """
    rotated = 0
    skipped = 0
    for connection in Connection.objects.all().iterator():
        try:
            new_access_token = rotate(connection.access_token)
            new_refresh_token = rotate(connection.refresh_token)
        except DecryptionError:
            skipped += 1
            continue
        with transaction.atomic():
            Connection.objects.filter(pk=connection.pk).update(
                access_token=new_access_token, refresh_token=new_refresh_token
            )
        rotated += 1
    return {"rotated": rotated, "skipped": skipped}

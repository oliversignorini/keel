"""``python manage.py rotate_connection_tokens`` (ddia#27). Run after
prepending a new key to ``KEEL_ENCRYPTION_KEY`` (comma-separated, newest
first — see ``config/settings/base.py``'s ``KEEL_ENCRYPTION_KEYS``) — moves
every ``Connection`` row's ``access_token`` / ``refresh_token`` onto that
new key, so the old key can eventually be dropped from the env var
without losing the ability to decrypt rows written under it.
"""

from typing import Any

from django.core.management.base import BaseCommand

from keel.connections.services import rotate_connection_tokens


class Command(BaseCommand):
    help = (
        "Re-encrypt every Connection.access_token/refresh_token under the "
        "current first KEEL_ENCRYPTION_KEY."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        result = rotate_connection_tokens()
        self.stdout.write(
            self.style.SUCCESS(
                f"Rotated {result['rotated']} connection(s); "
                f"skipped {result['skipped']} (no configured key could decrypt them)."
            )
        )
        if result["skipped"]:
            self.stderr.write(
                self.style.WARNING(
                    "Skipped rows still need their original key present in "
                    "KEEL_ENCRYPTION_KEY to ever be rotated or decrypted."
                )
            )

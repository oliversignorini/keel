"""Session-wide preconditions for the API test suite.

Everything here exists to turn a confusing failure into an instruction.
"""

from pathlib import Path

import pytest

# packages/emails is authored in .tsx and rendered to HTML at build time
# (PRD §4, Integration points: "Templates authored in react-email, rendered
# to HTML at build, sent from Django"). keel/notifications reads the built
# files, so without them every allauth flow that sends mail — signup, email
# verification, password reset — fails with an Internal Server Error several
# frames deep inside allauth, and the real cause is a missing build artifact.
#
# packages/emails/dist is a build artifact and is deliberately not committed,
# which means a fresh clone, a fresh worktree, and CI all start without it.
# Fail once, at the top, saying exactly what to run.
_EMAIL_DIST = Path(__file__).resolve().parents[2] / "packages" / "emails" / "dist"


def pytest_configure(config: pytest.Config) -> None:
    if not _EMAIL_DIST.is_dir() or not any(_EMAIL_DIST.glob("*.html")):
        raise pytest.UsageError(
            f"Email templates have not been built: {_EMAIL_DIST} is missing or empty.\n"
            "Run `pnpm --filter @keel/emails build` from the repo root first.\n"
            "Without it, every test that exercises signup, email verification or "
            "password reset fails inside allauth with an unrelated-looking 500."
        )


# Fixtures whose mere presence on a test means it opens a database
# connection, even when the test has no explicit `pytest.mark.django_db`.
# `client`/`admin_client`/`async_client` build a Django test client, which
# pytest-django backs with `db` internally; `live_server` starts a real
# server against the test database.
_DB_FIXTURE_NAMES = frozenset(
    {
        "db",
        "transactional_db",
        "django_db_reset_sequences",
        "django_db_serialized_rollback",
        "client",
        "admin_client",
        "admin_user",
        "async_client",
        "live_server",
    }
)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-apply the ``db`` marker to any test that touches the database,
    so ``-m "not db"``/``-m db`` split the suite without every test author
    having to remember a second marker on top of ``pytest.mark.django_db``.

    A test is considered DB-backed if it (or a fixture it uses) does any
    of: carries ``pytest.mark.django_db``, requests one of
    ``_DB_FIXTURE_NAMES`` (directly, or transitively through another
    fixture — ``item.fixturenames`` is already the fully resolved set),
    or is a ``django.test.TestCase``/``TransactionTestCase`` subclass
    (both start a DB transaction in ``setUpClass``/``_pre_setup``
    regardless of what the test body touches).
    """
    from django.test import TestCase, TransactionTestCase

    for item in items:
        marker_names = {marker.name for marker in item.iter_markers()}
        fixture_names = set(getattr(item, "fixturenames", ()))

        uses_db = bool("django_db" in marker_names or fixture_names & _DB_FIXTURE_NAMES)

        if not uses_db:
            test_cls = getattr(item, "cls", None)
            uses_db = test_cls is not None and issubclass(test_cls, (TestCase, TransactionTestCase))

        if uses_db:
            item.add_marker(pytest.mark.db)

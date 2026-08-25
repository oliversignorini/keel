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

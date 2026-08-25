"""The six transactional emails (PRD §5, docs/plans/phase-5.md 5.5).

Templates are authored in react-email under ``packages/emails/templates``
and rendered to static HTML **once, at build time**
(``pnpm --filter @keel/emails build``, wired into the repo's ``turbo run
build``) — not per send. The build renders each template with its
placeholder defaults still in place (``{{VERIFY_URL}}`` etc.), so the
files this module reads back out of ``packages/emails/dist`` are plain
HTML with those tokens still sitting in them; :func:`_render` does the
per-recipient substitution Django is actually responsible for.

This split keeps Node (JSX, react-email's build toolchain) out of the
request/task path entirely — Django never invokes Node at send time, so
a broken npm install on a worker box fails loudly at startup (a missing
file), never silently at send time with a half-rendered email.
"""

from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

EMAILS_DIST_DIR = Path(settings.BASE_DIR).parent.parent / "packages" / "emails" / "dist"


class EmailTemplateMissing(Exception):
    """Raised when ``packages/emails/dist/<name>.html`` doesn't exist —
    i.e. ``pnpm --filter @keel/emails build`` has not been run. Raised
    rather than silently falling back to some runtime-rendered
    alternative (docs/plans/phase-5.md 5.5 is explicit that a build
    failure must be reported, not papered over)."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(
            f"packages/emails/dist/{name}.html not found. Run "
            "`pnpm --filter @keel/emails build` before sending email."
        )


def _render(name: str, tokens: dict[str, str]) -> str:
    path = EMAILS_DIST_DIR / f"{name}.html"
    if not path.exists():
        raise EmailTemplateMissing(name)
    html = path.read_text(encoding="utf-8")
    for key, value in tokens.items():
        html = html.replace(f"{{{{{key}}}}}", value)
    return html


def _send(*, to: str, subject: str, template_name: str, tokens: dict[str, str]) -> None:
    html = _render(template_name, tokens)
    # Plain-text fallback lists every substituted value (in practice, the
    # links) rather than just the subject line — allauth's headless flow
    # tests extract confirmation/reset keys straight out of the plain
    # ``.body`` (see keel/accounts/tests/test_auth_flows.py's
    # ``_extract_key``), so the URL needs to be readable there too, not
    # only in the HTML alternative.
    body = "\n".join([subject, "", *tokens.values()])
    message = EmailMultiAlternatives(subject=subject, body=body, to=[to])
    message.attach_alternative(html, "text/html")
    message.send()


def send_verification_email(*, to: str, verify_url: str) -> None:
    _send(
        to=to,
        subject="Confirm your email address",
        template_name="verification",
        tokens={"VERIFY_URL": verify_url},
    )


def send_password_reset_email(*, to: str, reset_url: str) -> None:
    _send(
        to=to,
        subject="Reset your password",
        template_name="reset",
        tokens={"RESET_URL": reset_url},
    )


def send_invitation_email(*, to: str, organization_name: str, accept_url: str) -> None:
    _send(
        to=to,
        subject=f"You've been invited to {organization_name}",
        template_name="invitation",
        tokens={"ORGANIZATION_NAME": organization_name, "ACCEPT_URL": accept_url},
    )


def send_trial_ending_email(
    *, to: str, organization_name: str, billing_url: str, trial_end_date: str
) -> None:
    _send(
        to=to,
        subject="Your trial is ending soon",
        template_name="trial-ending",
        tokens={
            "ORGANIZATION_NAME": organization_name,
            "BILLING_URL": billing_url,
            "TRIAL_END_DATE": trial_end_date,
        },
    )


def send_payment_failed_email(*, to: str, organization_name: str, billing_url: str) -> None:
    _send(
        to=to,
        subject="Your payment didn't go through",
        template_name="payment-failed",
        tokens={"ORGANIZATION_NAME": organization_name, "BILLING_URL": billing_url},
    )


def send_seat_added_email(*, to: str, organization_name: str, member_email: str) -> None:
    _send(
        to=to,
        subject="A seat was added to your plan",
        template_name="seat-added",
        tokens={"ORGANIZATION_NAME": organization_name, "MEMBER_EMAIL": member_email},
    )

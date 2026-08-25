"""Routes allauth's verification and reset emails through the react-email
templates (PRD §5, docs/plans/phase-5.md 5.5: "verification and reset
emails must keep working through it" — "it" being
``HEADLESS_FRONTEND_URLS``, Phase 2's Next.js routes).

Overrides only ``send_mail``, allauth's one common send point for every
templated account email (see
``allauth.account.adapter.DefaultAccountAdapter.send_mail``) — every
other adapter method (confirmation-url construction, reset-key
generation) is untouched, so the ``activate_url`` / ``password_reset_url``
this receives already point at ``HEADLESS_FRONTEND_URLS``' Next.js routes.
An email type this adapter doesn't recognise (e.g. an allauth email this
project hasn't been asked to template — "account already exists") falls
back to allauth's own Django-template rendering rather than raising, so
adding allauth features later doesn't require touching this file first.
"""

from typing import Any

from allauth.account.adapter import DefaultAccountAdapter

from keel.notifications.emails import send_password_reset_email, send_verification_email


class KeelAccountAdapter(DefaultAccountAdapter):
    def send_mail(self, template_prefix: str, email: str, context: dict[str, Any]) -> None:
        if template_prefix in (
            "account/email/email_confirmation",
            "account/email/email_confirmation_signup",
        ):
            send_verification_email(to=email, verify_url=context["activate_url"])
            return
        if template_prefix == "account/email/password_reset_key":
            send_password_reset_email(to=email, reset_url=context["password_reset_url"])
            return
        super().send_mail(template_prefix, email, context)

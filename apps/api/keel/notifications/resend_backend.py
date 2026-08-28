"""Resend integration (PRD §5). A Django email
backend rather than a bespoke send path, so every call site — the six
templated sends in ``keel.notifications.emails``, allauth's own
``send_mail`` for account emails once ``ACCOUNT_ADAPTER`` routes through
them — goes through the same ``django.core.mail.send_mail`` /
``EmailMessage.send()`` surface regardless of environment. Dev and test
use Django's stock SMTP/locmem backends against Mailpit (settings.py);
this backend is wired in only for prod, as the ``default`` mailer.

Uses ``requests`` directly against Resend's HTTP API rather than adding
the ``resend`` SDK as a dependency — ``requests`` is already vendored
transitively (via ``stripe``), and the API surface used here is one POST.
"""

from collections.abc import Sequence
from typing import Any

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import EmailMessage

RESEND_API_URL = "https://api.resend.com/emails"


class ResendEmailBackend(BaseEmailBackend):
    # Django 6 moved backend construction to ``MAILERS`` (config/settings/
    # prod.py) and deprecated ``BaseEmailBackend.fail_silently`` — reading
    # the inherited attribute from a non-Django module raises a
    # RemovedInDjango70Warning — so this backend owns the flag itself and
    # takes it from the mailer's ``OPTIONS`` like any other option.
    def __init__(self, *, fail_silently: bool = False, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.fail_silently = fail_silently

    def send_messages(self, email_messages: Sequence[EmailMessage]) -> int:
        api_key = settings.RESEND_API_KEY
        if not api_key:
            raise ImproperlyConfigured(
                "RESEND_API_KEY is not set. Required in prod to send email via Resend."
            )
        sent = 0
        for message in email_messages:
            self._send_one(message, api_key)
            sent += 1
        return sent

    def _send_one(self, message: EmailMessage, api_key: str) -> None:
        payload: dict[str, Any] = {
            "from": message.from_email or settings.DEFAULT_FROM_EMAIL,
            "to": list(message.to),
            "subject": message.subject,
            "text": message.body,
        }
        alternatives = getattr(message, "alternatives", ())
        html_body = next(
            (content for content, mimetype in alternatives if mimetype == "text/html"),
            None,
        )
        if html_body is not None:
            payload["html"] = html_body

        response = requests.post(
            RESEND_API_URL,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if not self.fail_silently:
            response.raise_for_status()

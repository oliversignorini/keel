"""``POST /api/v1/stripe/webhook/`` (PRD §6; docs/plans/phase-4.md B.3) —
signature verification and the enqueue boundary. Processing behaviour and
the "replayed twice, identical state" requirement live in
``test_webhooks_replay.py``. Signatures are generated locally via
``stripe.WebhookSignature`` (pure HMAC, no network) — no real Stripe call,
no stripe-mock (PRD §4, "No credentials")."""

import json

import pytest
import stripe
from django.test import Client as APIClient

from keel.billing import tasks
from keel.billing.models import StripeEvent

pytestmark = pytest.mark.django_db

WEBHOOK_SECRET = "whsec_test_fixture_secret"


def _signed_request(event: dict) -> tuple[bytes, str]:
    body = json.dumps(event).encode()
    header = stripe.WebhookSignature.generate_signature_header(
        payload=body.decode(), secret=WEBHOOK_SECRET
    )
    return body, header


def _event(event_id: str = "evt_1", event_type: str = "invoice.paid") -> dict:
    return {
        "id": event_id,
        "type": event_type,
        "data": {"object": {"id": "obj_1", "customer": "cus_nonexistent"}},
    }


def test_webhook_rejects_unsigned_request(settings) -> None:
    settings.STRIPE_WEBHOOK_SECRET = WEBHOOK_SECRET

    response = APIClient().post(
        "/api/v1/stripe/webhook/", data=json.dumps(_event()), content_type="application/json"
    )

    assert response.status_code == 400
    assert not StripeEvent.objects.exists()


def test_webhook_rejects_wrongly_signed_request(settings) -> None:
    settings.STRIPE_WEBHOOK_SECRET = WEBHOOK_SECRET
    body, _correct_header = _signed_request(_event())

    response = APIClient().post(
        "/api/v1/stripe/webhook/",
        data=body,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE="t=1,v1=deadbeef",
    )

    assert response.status_code == 400
    assert not StripeEvent.objects.exists()


def test_webhook_accepts_correctly_signed_request(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.STRIPE_WEBHOOK_SECRET = WEBHOOK_SECRET
    dispatched = []
    monkeypatch.setattr(
        tasks.dispatch_stripe_event, "delay", lambda event_pk: dispatched.append(event_pk)
    )
    body, header = _signed_request(_event(event_id="evt_ok"))

    response = APIClient().post(
        "/api/v1/stripe/webhook/",
        data=body,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=header,
    )

    assert response.status_code == 200
    stripe_event = StripeEvent.objects.get(pk="evt_ok")
    assert stripe_event.type == "invoice.paid"
    assert dispatched == ["evt_ok"]


def test_webhook_replay_is_a_200_noop_and_does_not_redispatch(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.STRIPE_WEBHOOK_SECRET = WEBHOOK_SECRET
    dispatched = []
    monkeypatch.setattr(
        tasks.dispatch_stripe_event, "delay", lambda event_pk: dispatched.append(event_pk)
    )
    body, header = _signed_request(_event(event_id="evt_replay"))
    client = APIClient()

    first = client.post(
        "/api/v1/stripe/webhook/",
        data=body,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=header,
    )
    second = client.post(
        "/api/v1/stripe/webhook/",
        data=body,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=header,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert StripeEvent.objects.filter(pk="evt_replay").count() == 1
    assert dispatched == ["evt_replay"], "a replay must not re-enqueue processing"

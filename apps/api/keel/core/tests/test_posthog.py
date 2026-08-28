"""PostHog server-side capture (PRD §4 Integration points). No project
key exists for this project — what's provable
without one is the call shape, asserted here against the real client's
``capture`` method, patched rather than replaced (the client itself is
harmless to construct: ``disabled=True`` makes it a documented no-op with
no network calls — see ``keel.core.posthog``'s docstring)."""

from unittest.mock import patch

from keel.core.posthog import capture_billing_event, get_client, reset_client


def test_client_is_disabled_without_a_project_key(settings) -> None:
    settings.POSTHOG_PROJECT_API_KEY = ""
    reset_client()

    client = get_client()

    assert client.disabled is True


def test_client_is_enabled_when_a_project_key_is_configured(settings) -> None:
    settings.POSTHOG_PROJECT_API_KEY = "phc_real_key"
    reset_client()

    client = get_client()

    assert client.disabled is False
    reset_client()


def test_capture_billing_event_calls_the_client_with_the_right_shape(settings) -> None:
    settings.POSTHOG_PROJECT_API_KEY = "phc_real_key"
    reset_client()

    with patch.object(get_client(), "capture") as mock_capture:
        capture_billing_event(
            distinct_id="user-1",
            event="subscription_active",
            properties={"organization_id": "org-1", "plan_code": "starter"},
        )

    mock_capture.assert_called_once_with(
        distinct_id="user-1",
        event="subscription_active",
        properties={"organization_id": "org-1", "plan_code": "starter"},
    )
    reset_client()


def test_capture_billing_event_defaults_properties_to_an_empty_dict(settings) -> None:
    settings.POSTHOG_PROJECT_API_KEY = "phc_real_key"
    reset_client()

    with patch.object(get_client(), "capture") as mock_capture:
        capture_billing_event(distinct_id="user-1", event="invoice_paid")

    mock_capture.assert_called_once_with(distinct_id="user-1", event="invoice_paid", properties={})
    reset_client()

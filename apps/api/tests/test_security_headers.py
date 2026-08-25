"""Security headers (PRD §3 NFR "Security"; docs/plans/phase-8.md 8.6):
X-Content-Type-Options, Referrer-Policy, and a CSP on Django's own pages.
HSTS is prod.py's job (only correct over HTTPS) — see
config/settings/prod.py and docs/deploy-railway.md for that half."""

import pytest
from django.test import Client


@pytest.mark.django_db
def test_admin_login_carries_the_security_headers() -> None:
    response = Client().get("/admin/login/")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "same-origin"
    assert "Content-Security-Policy" in response.headers
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]


def test_api_responses_carry_the_security_headers() -> None:
    response = Client().get("/api/v1/schema/")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "same-origin"
    assert "Content-Security-Policy" in response.headers

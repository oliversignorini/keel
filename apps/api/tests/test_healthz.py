import pytest
from django.test import Client


@pytest.mark.django_db
def test_healthz_returns_200(client: Client) -> None:
    response = client.get("/healthz/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_does_not_touch_the_database(client: Client) -> None:
    """No @pytest.mark.django_db — a DB access here would raise."""
    response = client.get("/healthz/")

    assert response.status_code == 200

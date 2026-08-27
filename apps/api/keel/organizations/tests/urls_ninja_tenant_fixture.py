"""Test-only URLconf for ``ninja_tenant_isolation_fixtures.py`` — selected
via ``@pytest.mark.urls(...)`` so the fixture resources never touch the
real, production URLconf (``config.urls``)."""

from django.urls import path

from keel.organizations.tests.ninja_tenant_isolation_fixtures import fixture_api

urlpatterns = [
    path("api/v1/", fixture_api.urls),
]

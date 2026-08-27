"""Test-only URLconf for stage 10.A's scratch endpoint — see
``ninja_scratch_fixture.py``'s module docstring. Selected via
``@pytest.mark.urls(...)`` so the scratch resource never touches the
real, production URLconf (``config.urls``)."""

from django.urls import path

from keel.organizations.tests.ninja_scratch_fixture import scratch_api

urlpatterns = [
    path("api/v1/", scratch_api.urls),
]

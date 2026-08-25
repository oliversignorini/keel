"""Shared row builders for billing tests — no factory-boy, matching the
plain ``Model.objects.create`` style already used in
``keel.organizations.tests`` rather than introducing a second pattern."""

from keel.accounts.models import User
from keel.organizations.models import Organization

_counter = 0


def make_user(email: str | None = None) -> User:
    global _counter
    _counter += 1
    return User.objects.create_user(email=email or f"user-{_counter}@example.com", password="x")


def make_organization(name: str = "Acme", slug: str | None = None) -> Organization:
    global _counter
    _counter += 1
    creator = make_user()
    return Organization.objects.create(
        name=name, slug=slug or f"org-{_counter}", created_by=creator
    )

"""The ``settings.KEEL_ORGANIZATION_RESOLVER`` callable (PRD §4, "The
membership-resolution seam"; phase-3.md A.3).

``keel/core/authz.py`` cannot import this app, so it calls this function
by dotted path instead. Returning ``None`` means "this slug doesn't
resolve, or it does and the requester isn't an active member of it" —
deliberately the same outcome for both, so that a 404 never discloses an
organisation's existence to someone outside it (PRD invariant 7).
"""

from typing import Any

from keel.organizations.models import Membership, Organization


def resolve_organization(request: Any, org_slug: str) -> Organization | None:
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return (
        Organization.objects.filter(
            slug=org_slug,
            deleted_at__isnull=True,
            membership__user=user,
            membership__status=Membership.STATUS_ACTIVE,
        )
        .distinct()
        .first()
    )

"""Reads (PRD §4, "Data model"; CLAUDE.md invariant 1). Services mutate
and return; this module queries and returns. Nothing here writes.

``select_related`` is not an optimisation here, it is the contract
``tests/test_query_counts.py`` pins: the list endpoint is one query
regardless of row count.
"""

from django.db.models import QuerySet

from keel.__app__.models import __Resource__
from keel.organizations.models import Organization


def list___resources__(organization: Organization) -> QuerySet[__Resource__]:
    # keel:if no_fk
    return __Resource__.objects.for_organization(organization).select_related("created_by")
    # keel:endif
    # keel:if fk
    return __Resource__.objects.for_organization(organization).select_related(
        # keel:insert fk_select_related
    )
    # keel:endif

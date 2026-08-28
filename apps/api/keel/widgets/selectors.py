"""Reads (PRD §4, "Data model"; CLAUDE.md invariant 1). Services mutate
and return; this module queries and returns. Nothing here writes.

``select_related`` is not an optimisation here, it is the contract
``tests/test_query_counts.py`` pins: the list endpoint is one query
regardless of row count.
"""

from django.db.models import QuerySet

from keel.organizations.models import Organization
from keel.widgets.models import Widget


def list_widgets(organization: Organization) -> QuerySet[Widget]:
    return Widget.objects.for_organization(organization).select_related("created_by")

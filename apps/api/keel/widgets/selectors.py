"""Reads (PRD §4, "Data model"; docs/plans/phase-6.md 6.D). Services
mutate and return; this module queries and returns. Nothing here writes.
"""

from django.db.models import QuerySet

from keel.organizations.models import Organization
from keel.widgets.models import Widget


def list_widgets(organization: Organization) -> QuerySet[Widget]:
    return Widget.objects.for_organization(organization).select_related("created_by")

"""Reads (PRD §4, "Data model"). Services mutate and return; this module
queries and returns. Nothing here writes.

``list_files`` excludes ``deleted`` rows by default — a soft-deleted
upload is gone as far as any listing/retrieval caller is concerned, the
same way ``Organization.objects`` would filter out a soft-deleted org if
this template's org selectors did (``deleted_at`` isn't consulted there
today only because nothing yet lists organisations across a deletion
boundary). ``pending``/``failed``/``expired`` rows stay visible: a caller
watching an upload's progress needs to see it fail or expire, not have
it vanish from the list."""

from django.db.models import QuerySet

from keel.core.selectors import get_scoped_or_404
from keel.files.models import FileUpload
from keel.organizations.models import Organization


def list_files(organization: Organization) -> QuerySet[FileUpload]:
    return (
        FileUpload.objects.for_organization(organization)
        .exclude(status=FileUpload.STATUS_DELETED)
        .select_related("uploader")
        .order_by("-created_at")
    )


def files_for_organization(organization: Organization) -> QuerySet[FileUpload]:
    """Every row, including deleted ones — the scope ``get_upload_or_404``
    narrows to a single pk needs to reach a row ``list_files`` excludes
    (e.g. a deleted upload's own detail/download-URL/delete routes)."""
    return FileUpload.objects.for_organization(organization)


def get_upload_or_404(organization: Organization, file_id: str) -> FileUpload:
    return get_scoped_or_404(files_for_organization(organization), file_id)

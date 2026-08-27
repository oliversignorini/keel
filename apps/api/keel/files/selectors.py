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

from keel.files.models import FileUpload
from keel.organizations.models import Organization


def list_files(organization: Organization) -> QuerySet[FileUpload]:
    return (
        FileUpload.objects.for_organization(organization)
        .exclude(status=FileUpload.STATUS_DELETED)
        .select_related("uploader")
        .order_by("-created_at")
    )


def get_file(organization: Organization, file_id: str) -> FileUpload | None:
    return FileUpload.objects.for_organization(organization).filter(pk=file_id).first()

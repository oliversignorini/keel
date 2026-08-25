"""Presigned direct upload (PRD §5; docs/plans/phase-5.md 5.6): Django
issues the signature and records ``FileUpload``; the browser uploads
straight to R2; the row reaches ``complete``."""

from typing import Any

from keel.core.exceptions import UnprocessableEntity
from keel.core.ids import uuid7
from keel.files import r2_client
from keel.files.models import FileUpload


def _object_key(*, organization_id: Any, filename: str) -> str:
    """Organisation-scoped by construction, not merely by convention: the
    org id is the key's first path segment, so a presigned URL for one
    organisation's upload can never collide with — or be guessed into —
    another's (docs/plans/phase-5.md 5.6, "organisation-scoped and
    unreadable across tenants")."""
    return f"org/{organization_id}/{uuid7()}/{filename}"


def create_presigned_upload(
    *, organization: Any, uploader: Any, filename: str, content_type: str, size: int
) -> tuple[FileUpload, str]:
    key = _object_key(organization_id=organization.pk, filename=filename)
    file_upload = FileUpload.objects.create(
        organization=organization,
        uploader=uploader,
        key=key,
        content_type=content_type,
        size=size,
    )
    upload_url = r2_client.generate_presigned_upload(key=key, content_type=content_type)
    return file_upload, upload_url


def complete_upload(*, file_upload: FileUpload) -> FileUpload:
    """Moves ``file_upload`` to ``complete`` only once the object is
    actually confirmed present in the bucket (PRD §5.6's acceptance
    criterion is "reaches complete", not "was told to") — trusting the
    browser's completion call alone would let a client mark a row
    complete for a PUT that failed or never happened."""
    if not r2_client.object_exists(key=file_upload.key):
        raise UnprocessableEntity(
            code="upload_not_found", message="No object was found at the presigned key yet."
        )
    file_upload.status = FileUpload.STATUS_COMPLETE
    file_upload.save(update_fields=["status"])
    return file_upload

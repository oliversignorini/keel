"""Presigned direct upload (PRD §5; docs/plans/phase-5.md 5.6): Django
issues the signature and records ``FileUpload``; the browser uploads
straight to R2; the row reaches ``complete``."""

from typing import Any

from keel.core.audit import audited, not_audited
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


@audited("file.upload_presigned")
def create_presigned_upload(
    *, organization: Any, actor: Any, filename: str, content_type: str, size: int
) -> tuple[FileUpload, str]:
    key = _object_key(organization_id=organization.pk, filename=filename)
    file_upload = FileUpload.objects.create(
        organization=organization,
        uploader=actor,
        key=key,
        content_type=content_type,
        size=size,
    )
    upload_url = r2_client.generate_presigned_upload(key=key, content_type=content_type)
    return file_upload, upload_url


@not_audited(
    reason="Server-side confirmation that an R2 object exists; the user-initiated "
    "action is create_presigned_upload above, which is audited. This call carries "
    "no actor (it fires from the browser's completion callback with only the "
    "FileUpload row) and records no new fact beyond a status flip already implied "
    "by the presigned-upload row."
)
def complete_upload(*, file_upload: FileUpload) -> FileUpload:
    """Moves ``file_upload`` to ``complete`` only once the object is
    actually confirmed present in the bucket (PRD §5.6's acceptance
    criterion is "reaches complete", not "was told to") — trusting the
    browser's completion call alone would let a client mark a row
    complete for a PUT that failed or never happened.

    The transition itself is a guarded ``UPDATE ... WHERE status =
    pending`` (ddia#21), not an unconditional assignment: two concurrent
    completion calls for the same upload both pass the ``object_exists``
    check, but only one can move the row from ``pending``. The other's
    update matches zero rows — treated as already-complete, not an
    error, since that's exactly what it is."""
    if not r2_client.object_exists(key=file_upload.key):
        raise UnprocessableEntity(
            code="upload_not_found", message="No object was found at the presigned key yet."
        )
    FileUpload.objects.filter(pk=file_upload.pk, status=FileUpload.STATUS_PENDING).update(
        status=FileUpload.STATUS_COMPLETE
    )
    file_upload.refresh_from_db()
    return file_upload

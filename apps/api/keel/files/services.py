"""Presigned direct upload: Django issues the upload URL and records
``FileUpload``; the browser uploads straight to storage; the row reaches
``available``. See ``keel.files.models`` for the full state machine."""

import re
from typing import Any

from django.conf import settings
from django.db import transaction

from keel.core.audit import audited, not_audited
from keel.core.exceptions import Conflict, UnprocessableEntity
from keel.core.ids import uuid7
from keel.files import storage
from keel.files.models import FileUpload

_CHECKSUM_RE = re.compile(r"^[0-9a-f]{64}$")
# Conservative default extension: alnum only, capped at 10 characters
# (covers every real document/image/archive extension this template's
# acceptance criteria care about) so an attacker-controlled filename
# can't smuggle a path segment or a wildly long suffix into the key.
_SAFE_EXTENSION_RE = re.compile(r"^[A-Za-z0-9]{1,10}$")
# Filename is display-only (never part of the storage key — see
# _object_key below) but still gets rendered back to the uploader's own
# browser, so control characters and path separators are stripped here
# rather than trusted through.
_UNSAFE_FILENAME_CHARS_RE = re.compile(r"[\x00-\x1f/\\]")


def _sanitize_filename(filename: str) -> str:
    cleaned = _UNSAFE_FILENAME_CHARS_RE.sub("", filename).strip()
    return cleaned[:255] or "upload"


def _safe_extension(filename: str) -> str:
    _, _dot, extension = filename.rpartition(".")
    if not extension or not _SAFE_EXTENSION_RE.match(extension):
        return ""
    return f".{extension.lower()}"


def _object_key(*, organization_id: Any, filename: str) -> str:
    """Organisation-scoped by construction, not merely by convention: the
    org id is the key's first path segment, so a presigned URL for one
    organisation's upload can never collide with — or be guessed into —
    another's. The uploader's filename is deliberately *not* interpolated
    here — only a whitelisted extension survives, so a filename can never
    change the key's shape or traverse a path."""
    return f"org/{organization_id}/{uuid7()}{_safe_extension(filename)}"


def _check_upload_policy(*, content_type: str, size: int) -> None:
    max_size = settings.FILES_MAX_UPLOAD_SIZE_BYTES
    if size > max_size:
        raise UnprocessableEntity(
            code="upload_too_large",
            message=f"File exceeds the {max_size}-byte upload limit.",
        )
    allowed = settings.FILES_ALLOWED_CONTENT_TYPES
    if allowed and content_type not in allowed:
        raise UnprocessableEntity(
            code="content_type_not_allowed",
            message=f"Content type '{content_type}' is not permitted.",
        )


@audited("file.upload_presigned")
def create_presigned_upload(
    *,
    organization: Any,
    actor: Any,
    filename: str,
    content_type: str,
    size: int,
    checksum_sha256: str,
) -> tuple[FileUpload, str]:
    checksum_sha256 = checksum_sha256.lower()
    if not _CHECKSUM_RE.match(checksum_sha256):
        raise UnprocessableEntity(
            code="invalid_checksum", message="checksum_sha256 must be 64 hex characters."
        )
    _check_upload_policy(content_type=content_type, size=size)
    key = _object_key(organization_id=organization.pk, filename=filename)
    file_upload = FileUpload.objects.create(
        organization=organization,
        uploader=actor,
        filename=_sanitize_filename(filename),
        key=key,
        content_type=content_type,
        size=size,
        checksum_sha256=checksum_sha256,
    )
    adapter = storage.get_storage()
    upload_url = adapter.generate_presigned_upload(
        key=key,
        content_type=content_type,
        organization_slug=organization.slug,
        file_upload_id=str(file_upload.id),
    )
    return file_upload, upload_url


def _fail(file_upload: FileUpload, *, reason: str) -> FileUpload:
    updated = FileUpload.objects.filter(pk=file_upload.pk, status=FileUpload.STATUS_PENDING).update(
        status=FileUpload.STATUS_FAILED, failure_reason=reason
    )
    if updated:
        file_upload.refresh_from_db()
    return file_upload


@not_audited(
    reason="Server-side confirmation that a storage object exists; the user-initiated "
    "action is create_presigned_upload above, which is audited. This call carries "
    "no actor (it fires from the browser's completion callback with only the "
    "FileUpload row) and records no new fact beyond a status flip already implied "
    "by the presigned-upload row."
)
def complete_upload(*, file_upload: FileUpload) -> FileUpload:
    """Moves ``file_upload`` to ``available`` only once the object is
    actually confirmed present in storage — trusting the browser's
    completion call alone would let a client mark a row available for a
    PUT that failed or never happened.

    Every fact recorded below comes from the storage provider's own
    ``HeadObject``, never from the client — ``size`` and
    ``content_type`` are overwritten with what was actually observed,
    and the checksum the client declared at create time is verified
    against the actual bytes (``storage.compute_sha256``) before the row
    is allowed to reach ``available``. A mismatch — or an observed
    size/content-type outside the configured policy — moves the row to
    ``failed`` instead of raising into a 500, since a corrupted or
    policy-violating upload is an expected outcome, not a bug.

    Every transition is a guarded ``UPDATE ... WHERE status = pending``,
    not an unconditional assignment: two concurrent completion calls
    for the same upload both pass the ``head_object``
    check, but only one can move the row out of ``pending``. The other's
    update matches zero rows — treated as already-decided, not an
    error, since that's exactly what it is."""
    adapter = storage.get_storage()
    metadata = adapter.head_object(key=file_upload.key)
    if metadata is None:
        raise UnprocessableEntity(
            code="upload_not_found", message="No object was found at the presigned key yet."
        )

    try:
        _check_upload_policy(content_type=metadata.content_type, size=metadata.size)
    except UnprocessableEntity as exc:
        return _fail(file_upload, reason=exc.code)

    observed_checksum = adapter.compute_sha256(key=file_upload.key)
    if observed_checksum != file_upload.checksum_sha256:
        return _fail(file_upload, reason="checksum_mismatch")

    with transaction.atomic():
        from django.utils import timezone

        updated = FileUpload.objects.filter(
            pk=file_upload.pk, status=FileUpload.STATUS_PENDING
        ).update(
            status=FileUpload.STATUS_AVAILABLE,
            size=metadata.size,
            content_type=metadata.content_type,
            etag=metadata.etag,
            completed_at=timezone.now(),
        )
    if updated:
        file_upload.refresh_from_db()
    return file_upload


def _dispatch_object_purge(file_upload_id: Any) -> None:
    from keel.files.tasks import purge_deleted_file_object_task

    purge_deleted_file_object_task.enqueue(str(file_upload_id))


@not_audited(
    reason="System-triggered storage cleanup for an already-tombstoned row — either "
    "the Tier-1 dispatch from delete_file's on_commit above, or the backstop sweep "
    "(keel.files.tasks.sweep_stale_uploads) retrying a purge that never landed. No "
    "actor: the user-initiated action is delete_file, already audited above, and "
    "this records no new fact beyond the object_purged flag an already-deleted row "
    "implies."
)
def purge_deleted_file_object(*, file_upload_id: Any) -> None:
    """The one service call both ``tasks.purge_deleted_file_object_task``
    (Tier-1, per-row) and ``tasks.sweep_stale_uploads`` (the beat
    backstop) delegate to — kept as a single idempotent function rather
    than duplicated in each, since "delete an object and flip a flag" is
    the same operation regardless of what triggered it."""
    file_upload = FileUpload.objects.filter(
        pk=file_upload_id, status=FileUpload.STATUS_DELETED
    ).first()
    if file_upload is None or file_upload.object_purged:
        return
    storage.get_storage().delete_object(key=file_upload.key)
    FileUpload.objects.filter(pk=file_upload.pk, object_purged=False).update(object_purged=True)


@audited("file.deleted")
def delete_file(*, file_upload: FileUpload, actor: Any) -> FileUpload:
    """A tombstone, not a row delete: the ``deleted`` state is what
    drives storage-object cleanup. Deleting
    the row outright would either leave the storage object orphaned
    forever (nothing left to know it needs cleaning up) or force the
    delete to do a synchronous storage call inside the request — this
    way the row itself is the durable record that cleanup is owed, and
    the actual object removal happens out-of-band (the fire-and-forget
    task dispatched on commit below, backstopped by
    ``keel.files.tasks.sweep_stale_uploads`` for the case the dispatch
    itself never reaches the broker).

    Guarded like every other transition: only a row that is currently
    ``available`` or ``failed`` can move to ``deleted`` — a ``pending``
    or ``expired`` upload has no object worth tombstoning and raises
    instead. Deleting an already-``deleted`` row is treated as a no-op,
    the same idempotent-delete convention as everywhere else in this
    codebase, rather than an error — including the case where a second,
    concurrent delete call loses the compare-and-set below."""
    from django.utils import timezone

    if file_upload.status == FileUpload.STATUS_DELETED:
        return file_upload
    if file_upload.status not in (FileUpload.STATUS_AVAILABLE, FileUpload.STATUS_FAILED):
        raise Conflict(
            code="not_deletable",
            message=f"An upload in '{file_upload.status}' status cannot be deleted.",
        )

    with transaction.atomic():
        updated = FileUpload.objects.filter(
            pk=file_upload.pk,
            status__in=(FileUpload.STATUS_AVAILABLE, FileUpload.STATUS_FAILED),
        ).update(status=FileUpload.STATUS_DELETED, deleted_at=timezone.now())
        if updated:
            transaction.on_commit(lambda: _dispatch_object_purge(file_upload.pk))
    if updated:
        file_upload.refresh_from_db()
    return file_upload

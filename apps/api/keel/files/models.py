"""FileUpload (PRD §4 "Data model"). Presigned direct upload from the
browser to storage; Django issues the upload URL and records this row.

Five states, not two (ddia#21 — the phase-5 model had only ``pending`` /
``complete``, "the state set Phase 13 will need most of those, and
adding states to a machine that already has rows in it is harder than
designing them in"):

    pending --> available   (services.complete_upload: checksum verified,
                              size/content_type/etag taken from the
                              storage provider's own HeadObject, never
                              the client)
    pending --> failed      (services.complete_upload: checksum mismatch,
                              or the observed object violates the
                              configured size/content-type limits)
    pending --> expired     (keel.files.tasks.sweep_stale_uploads: no
                              completion call within FILES_PENDING_UPLOAD_TTL)
    {available, failed}
        --> deleted         (services.delete_file: a tombstone, not a row
                              delete — see that function's docstring for
                              why, and keel.files.tasks for what drives
                              the actual storage-object cleanup off it)

Every transition above is a guarded compare-and-set (``UPDATE ... WHERE
status = <expected>``), not an unconditional assignment — see
``services.py``."""

from django.db import models

from keel.core.models import OrgScopedModel


class FileUpload(OrgScopedModel):
    STATUS_PENDING = "pending"
    STATUS_AVAILABLE = "available"
    STATUS_FAILED = "failed"
    STATUS_EXPIRED = "expired"
    STATUS_DELETED = "deleted"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_AVAILABLE, "Available"),
        (STATUS_FAILED, "Failed"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_DELETED, "Deleted"),
    )

    # ddia#21 "reconsider organization CASCADE on FileUpload": every
    # other ``OrgScopedModel`` inherits ``CASCADE`` from the base class,
    # which is right for rows that are pure metadata — but a
    # cascade-deleted ``FileUpload`` row silently orphans its storage
    # object forever, with no tombstone left to drive cleanup from. This
    # app's own delete path never hits that (``delete_file`` below is a
    # tombstone update, and ``organizations.services.delete_organization``
    # is itself a soft delete — see that function), but a hard delete of
    # an ``Organization`` row from anywhere else (Django admin, a future
    # GDPR-erasure command, a shell) must not be allowed to make a
    # storage object unreachable without anyone deciding that on purpose.
    # PROTECT forces that decision to go through this app's own
    # tombstone-and-sweep path instead.
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        db_index=True,
    )

    uploader = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="file_uploads"
    )
    # Display-only (ddia#21: "sanitise filename out of the object key ...
    # keep it as a display-only column") — never interpolated into
    # ``key``, which is generated from a uuid7 alone (services._object_key).
    filename = models.CharField(max_length=255)
    key = models.CharField(max_length=1024, unique=True)
    content_type = models.CharField(max_length=255)
    size = models.BigIntegerField()
    # Client-declared at create time (what the browser is about to
    # upload); services.complete_upload verifies it against the bytes
    # storage actually received and rejects the completion on mismatch —
    # this is what makes "verified" true rather than aspirational.
    checksum_sha256 = models.CharField(max_length=64)
    # Set only once the object is confirmed present — the storage
    # provider's own ETag, taken from HeadObject, never the client.
    etag = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    failure_reason = models.CharField(max_length=64, blank=True, default="")
    completed_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    # Flipped by the tombstone sweep once the underlying storage object
    # is confirmed gone — lets the sweep be a safe, idempotent retry
    # rather than a fire-and-forget it can only run once.
    object_purged = models.BooleanField(default=False)

    class Meta:
        indexes = (
            models.Index(fields=["organization", "created_at"]),
            # Both sweeps (keel.files.tasks) filter on status first —
            # stale-pending by status + created_at, tombstone cleanup by
            # status + object_purged.
            models.Index(fields=["status", "created_at"]),
        )
        constraints = (
            models.CheckConstraint(
                name="file_upload_size_non_negative",
                condition=models.Q(size__gte=0),
            ),
            models.CheckConstraint(
                name="file_upload_checksum_sha256_is_hex64",
                condition=models.Q(checksum_sha256__regex=r"^[0-9a-f]{64}$"),
            ),
            # One direction each, not iff: a row moves through several
            # states before (maybe) reaching "deleted"/"available", and
            # the timestamp is set exactly once, on the transition into
            # that state — never cleared going forward. What these rule
            # out is the timestamp being set on a row that never reached
            # (or, for completed_at, moved past) the matching status.
            # String literals, not the class attributes above: a nested
            # ``Meta`` class body can't see ``FileUpload``'s own
            # namespace (it isn't defined yet while its body is still
            # executing) — these must match STATUS_DELETED / STATUS_AVAILABLE.
            models.CheckConstraint(
                name="file_upload_deleted_at_requires_deleted_status",
                condition=models.Q(deleted_at__isnull=True) | models.Q(status="deleted"),
            ),
            models.CheckConstraint(
                name="file_upload_completed_at_requires_reached_available",
                condition=models.Q(completed_at__isnull=True)
                | models.Q(status__in=("available", "deleted")),
            ),
        )

    def __str__(self) -> str:
        return self.key

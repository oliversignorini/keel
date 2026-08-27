"""Two tasks, two different shapes (PRD §4 invariant 5), same split
``keel.billing.tasks`` already draws:

- ``purge_deleted_file_object_task`` is Tier-1 (``keel.core.tasks``):
  fire-and-forget, dispatched from ``services.delete_file`` on commit.
  Deleting an object that's already gone is a no-op
  (``ObjectStorage.delete_object``'s own contract), so a retry after a
  transient storage failure is always safe.
- ``sweep_stale_uploads`` is a plain Celery beat task, wired into
  ``CELERY_BEAT_SCHEDULE`` (config/settings/base.py) via
  ``config/celery.py``'s ``QUEUE_SCHEDULED`` routing, the same pattern as
  ``keel.billing.tasks.sweep_unprocessed_stripe_events``. It does two
  independent jobs, both from ddia#21:

  1. Expires ``pending`` rows nobody ever completed
     (``FILES_PENDING_UPLOAD_TTL_SECONDS``) — "a beat sweeper for stale
     pending rows", so an abandoned upload doesn't accumulate forever.
  2. Retries the object-purge for any ``deleted`` row whose
     ``object_purged`` flag never flipped — the backstop for the
     fire-and-forget dispatch above never reaching the broker at all
     (the same gap ``sweep_unprocessed_stripe_events`` covers for
     webhooks), so a tombstoned row's object isn't left behind forever
     just because one dispatch was lost.

  Both halves are idempotent when run twice: an already-expired row
  doesn't match the ``pending`` filter a second time, and an
  already-purged row doesn't match ``object_purged=False`` a second
  time — see ``keel/files/tests/test_sweep.py``, which runs the sweep
  twice and asserts identical state, the same discipline
  ``keel.jobs.tasks`` documents for its own six scheduled jobs.
"""

from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from keel.core.tasks import task
from keel.files import services
from keel.files.models import FileUpload


@task
def purge_deleted_file_object_task(file_upload_id: str) -> None:
    services.purge_deleted_file_object(file_upload_id=file_upload_id)


@shared_task(name="keel.files.tasks.sweep_stale_uploads")
def sweep_stale_uploads() -> dict[str, int]:
    ttl_threshold = timezone.now() - timedelta(seconds=settings.FILES_PENDING_UPLOAD_TTL_SECONDS)
    expired_ids = list(
        FileUpload.objects.filter(
            status=FileUpload.STATUS_PENDING, created_at__lt=ttl_threshold
        ).values_list("pk", flat=True)
    )
    for file_id in expired_ids:
        FileUpload.objects.filter(pk=file_id, status=FileUpload.STATUS_PENDING).update(
            status=FileUpload.STATUS_EXPIRED
        )

    unpurged_ids = list(
        FileUpload.objects.filter(
            status=FileUpload.STATUS_DELETED, object_purged=False
        ).values_list("pk", flat=True)
    )
    for file_id in unpurged_ids:
        services.purge_deleted_file_object(file_upload_id=file_id)

    return {"expired": len(expired_ids), "purged": len(unpurged_ids)}

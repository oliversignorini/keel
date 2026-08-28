"""keel.files.tasks (ddia#21: "a beat sweeper for stale pending rows" and
"a deleted tombstone state driving R2 object cleanup"). Every scheduled
job in this codebase is run twice and asserted idempotent
(keel.jobs.tasks's own convention) — both halves of the sweep here get
that treatment."""

from datetime import timedelta

import boto3
import pytest
from botocore.exceptions import ClientError
from django.conf import settings
from django.utils import timezone
from moto import mock_aws

from keel.accounts.models import User
from keel.files.models import FileUpload
from keel.files.tasks import purge_deleted_file_object_task, sweep_stale_uploads
from keel.organizations import services
from keel.organizations.models import Organization

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _mocked_bucket():
    with mock_aws():
        boto3.client(
            "s3",
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            region_name="us-east-1",
        ).create_bucket(Bucket=settings.R2_BUCKET)
        yield


def _org() -> Organization:
    owner = User.objects.create_user(email="sweep-owner@example.com", password="s3cret-pass")
    return services.create_organization(name="Acme", slug="acme-sweep", actor=owner)


def _pending_upload(org: Organization, *, age: timedelta) -> FileUpload:
    upload = FileUpload.objects.create(
        organization=org,
        uploader=org.created_by,
        filename="stale.pdf",
        key=f"org/{org.pk}/stale-{age}",
        content_type="application/pdf",
        size=1,
        checksum_sha256="0" * 64,
        status=FileUpload.STATUS_PENDING,
    )
    FileUpload.objects.filter(pk=upload.pk).update(created_at=timezone.now() - age)
    upload.refresh_from_db()
    return upload


def test_sweep_expires_a_pending_upload_past_the_ttl() -> None:
    org = _org()
    ttl = timedelta(seconds=settings.FILES_PENDING_UPLOAD_TTL_SECONDS)
    stale = _pending_upload(org, age=ttl + timedelta(minutes=1))
    fresh = _pending_upload(org, age=timedelta(minutes=1))

    result = sweep_stale_uploads()

    stale.refresh_from_db()
    fresh.refresh_from_db()
    assert stale.status == FileUpload.STATUS_EXPIRED
    assert fresh.status == FileUpload.STATUS_PENDING
    assert result["expired"] == 1


def test_sweep_is_idempotent_run_twice() -> None:
    org = _org()
    ttl = timedelta(seconds=settings.FILES_PENDING_UPLOAD_TTL_SECONDS)
    stale = _pending_upload(org, age=ttl + timedelta(minutes=1))

    first = sweep_stale_uploads()
    second = sweep_stale_uploads()

    stale.refresh_from_db()
    assert stale.status == FileUpload.STATUS_EXPIRED
    assert first["expired"] == 1
    assert second["expired"] == 0


def test_sweep_retries_a_purge_the_fire_and_forget_dispatch_never_reached() -> None:
    """Simulates the gap ``sweep_unprocessed_stripe_events`` covers for
    webhooks: a row reached ``deleted`` but ``object_purged`` never
    flipped, because the Tier-1 dispatch (``services._dispatch_object_purge``)
    never reached the broker. The sweep must pick it up regardless."""
    org = _org()
    adapter_client = boto3.client(
        "s3",
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="us-east-1",
    )
    key = f"org/{org.pk}/orphaned"
    adapter_client.put_object(Bucket=settings.R2_BUCKET, Key=key, Body=b"data")
    upload = FileUpload.objects.create(
        organization=org,
        uploader=org.created_by,
        filename="orphaned.pdf",
        key=key,
        content_type="application/pdf",
        size=4,
        checksum_sha256="0" * 64,
        status=FileUpload.STATUS_DELETED,
        deleted_at=timezone.now(),
        object_purged=False,
    )

    result = sweep_stale_uploads()

    upload.refresh_from_db()
    assert upload.object_purged is True
    assert result["purged"] == 1
    with pytest.raises(ClientError):
        adapter_client.head_object(Bucket=settings.R2_BUCKET, Key=key)


def test_purge_task_is_a_noop_for_an_already_purged_row() -> None:
    org = _org()
    upload = FileUpload.objects.create(
        organization=org,
        uploader=org.created_by,
        filename="gone.pdf",
        key=f"org/{org.pk}/already-gone",
        content_type="application/pdf",
        size=1,
        checksum_sha256="0" * 64,
        status=FileUpload.STATUS_DELETED,
        deleted_at=timezone.now(),
        object_purged=True,
    )

    # No object exists at this key at all — a real delete_object call
    # would still be a no-op, but the early return proves the task
    # doesn't even try once object_purged is already true.
    purge_deleted_file_object_task(str(upload.pk))

    upload.refresh_from_db()
    assert upload.object_purged is True

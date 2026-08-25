"""The one seam that knows this is S3-shaped storage (PRD §5;
docs/plans/phase-5.md 5.6). R2 and the dev-time MinIO stand-in both speak
the S3 API, so this module is unchanged between environments — only
``settings.R2_*`` (endpoint, credentials, bucket) differs."""

from typing import Any

import boto3
from django.conf import settings

PRESIGNED_URL_EXPIRY_SECONDS = 600


def _client() -> Any:
    # ``endpoint_url=None`` (test settings) falls through to boto3's own
    # default AWS endpoint resolution — what lets ``moto``'s mocked S3
    # intercept these calls in tests. Dev/prod always set a real
    # endpoint (MinIO / R2), so this branch is test-only.
    kwargs: dict[str, Any] = {
        "aws_access_key_id": settings.R2_ACCESS_KEY_ID,
        "aws_secret_access_key": settings.R2_SECRET_ACCESS_KEY,
        "region_name": "us-east-1",
    }
    if settings.R2_ENDPOINT_URL:
        kwargs["endpoint_url"] = settings.R2_ENDPOINT_URL
    return boto3.client("s3", **kwargs)


def generate_presigned_upload(*, key: str, content_type: str) -> str:
    """A presigned PUT URL the browser uploads straight to — Django never
    proxies the file's bytes (PRD §5, "the browser uploads straight to
    R2")."""
    url: str = _client().generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.R2_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=PRESIGNED_URL_EXPIRY_SECONDS,
    )
    return url


def generate_presigned_download(*, key: str) -> str:
    url: str = _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.R2_BUCKET, "Key": key},
        ExpiresIn=PRESIGNED_URL_EXPIRY_SECONDS,
    )
    return url


def object_exists(*, key: str) -> bool:
    """Used at ``complete`` time to confirm the browser's direct upload
    actually landed before ``FileUpload.status`` moves to ``complete`` —
    trusting the browser's say-so alone would let a client mark a row
    complete for an object that was never uploaded."""
    from botocore.exceptions import ClientError

    try:
        _client().head_object(Bucket=settings.R2_BUCKET, Key=key)
    except ClientError:
        return False
    return True


def ensure_bucket_exists() -> None:
    """Dev/test convenience — neither MinIO nor moto pre-creates a
    bucket. Never called in prod (R2 buckets are provisioned out of
    band)."""
    from botocore.exceptions import ClientError

    client = _client()
    try:
        client.head_bucket(Bucket=settings.R2_BUCKET)
    except ClientError:
        client.create_bucket(Bucket=settings.R2_BUCKET)

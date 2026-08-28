"""The storage seam ("Introduce the storage seam via Django's
``STORAGES`` setting"). ``keel.files.r2_client`` was a concrete boto3
client, not an adapter — every call site imported it directly, so
swapping providers meant editing code. This module
replaces it with ``ObjectStorage``, a small protocol every provider
implements, selected through Django's own ``STORAGES["files"]`` alias
(``config/settings/base.py``): change ``KEEL_FILES_STORAGE_BACKEND`` and
nothing in ``services.py`` or ``views.py`` changes.

Two implementations ship:

- ``S3CompatibleStorage`` — boto3 against any S3-compatible endpoint.
  MinIO in dev, R2 in production, moto in tests (unchanged from the
  earlier ``r2_client.py``, just reorganised behind the protocol).
- ``LocalFileSystemStorage`` — plain disk, for a developer who wants
  ``python manage.py runserver`` to work without also running MinIO.
  There is no S3-shaped "presign a PUT" primitive for a local disk, so
  its "presigned" upload URL is an ordinary session-authenticated app
  route (``PUT .../local-object/``) rather than a bucket URL — see
  ``keel.files.views.local_object_upload``.

docs/storage.md documents the provider matrix and the production
caveats (Railway volumes included) this module is deliberately silent
on — this file is the mechanism, that doc is the judgement call.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

PRESIGNED_URL_EXPIRY_SECONDS = 600

# Read in fixed-size chunks wherever object bytes are streamed (checksum
# verification, local writes) so a large upload never loads its whole
# body into memory at once.
_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class ObjectMetadata:
    """What ``head_object`` reports about an object actually present in
    storage — the server's own observation, never the client's claim:
    size, content type and etag all come from ``HeadObject``."""

    size: int
    content_type: str
    etag: str


class ObjectStorage(Protocol):
    """The seam every provider implements. Nothing in ``services.py``
    imports boto3 or ``pathlib`` directly — only this protocol.

    ``organization_slug``/``file_upload_id`` are unused by the S3-shaped
    backend (its URL is a signed bucket URL, keyed on ``key`` alone) but
    are threaded through uniformly so ``LocalFileSystemStorage`` can
    build its own-app-route URL without every call site needing to know
    which backend is active."""

    def generate_presigned_upload(
        self, *, key: str, content_type: str, organization_slug: str, file_upload_id: str
    ) -> str: ...

    def generate_presigned_download(
        self, *, key: str, organization_slug: str, file_upload_id: str
    ) -> str: ...

    def head_object(self, *, key: str) -> ObjectMetadata | None: ...

    def compute_sha256(self, *, key: str) -> str | None:
        """Streams the object back and hashes it. Downloading a
        just-uploaded object to verify its checksum trades a second
        server-side transfer for a guarantee neither MinIO nor R2 can be
        relied on to enforce for us (real S3 validates an
        ``x-amz-checksum-sha256`` header against the uploaded bytes;
        moto — this project's test double — accepts the header
        as-supplied without checking it, so a test asserting rejection
        would only be proving moto trusts the client, the opposite of
        the property this check needs). Acceptable for the document sizes
        this template targets; a provider whose checksum feature is
        trustworthy in production is a future optimisation, not a
        correctness requirement — see docs/storage.md."""
        ...

    def delete_object(self, *, key: str) -> None:
        """Idempotent: deleting an already-absent key is not an error —
        the sweeper (``keel.files.tasks``) and a user-initiated delete
        can both race to remove the same object."""
        ...

    def ensure_ready(self) -> None:
        """Dev/test convenience only — create the bucket/directory if
        it doesn't exist yet. Never called in production."""
        ...


class S3CompatibleStorage:
    """MinIO, Cloudflare R2, or real S3 — all three speak the same API,
    so one implementation covers dev-with-MinIO, staging, and
    production; only ``STORAGES["files"]["OPTIONS"]`` differs."""

    def __init__(
        self,
        *,
        endpoint_url: str = "",
        access_key_id: str = "",
        secret_access_key: str = "",
        bucket: str = "",
    ) -> None:
        self._endpoint_url = endpoint_url
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._bucket = bucket

    def _client(self) -> Any:
        import boto3

        # ``endpoint_url=""`` (test settings) falls through to boto3's
        # own default AWS endpoint resolution — what lets moto's mocked
        # S3 intercept these calls. Dev/prod always set a real endpoint
        # (MinIO / R2), so this branch is test-only.
        kwargs: dict[str, Any] = {
            "aws_access_key_id": self._access_key_id,
            "aws_secret_access_key": self._secret_access_key,
            "region_name": "us-east-1",
        }
        if self._endpoint_url:
            kwargs["endpoint_url"] = self._endpoint_url
        return boto3.client("s3", **kwargs)

    def generate_presigned_upload(
        self, *, key: str, content_type: str, organization_slug: str = "", file_upload_id: str = ""
    ) -> str:
        url: str = self._client().generate_presigned_url(
            "put_object",
            Params={"Bucket": self._bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=PRESIGNED_URL_EXPIRY_SECONDS,
        )
        return url

    def generate_presigned_download(
        self, *, key: str, organization_slug: str = "", file_upload_id: str = ""
    ) -> str:
        url: str = self._client().generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=PRESIGNED_URL_EXPIRY_SECONDS,
        )
        return url

    def head_object(self, *, key: str) -> ObjectMetadata | None:
        from botocore.exceptions import ClientError

        try:
            response = self._client().head_object(Bucket=self._bucket, Key=key)
        except ClientError:
            return None
        return ObjectMetadata(
            size=int(response["ContentLength"]),
            content_type=response.get("ContentType", ""),
            etag=response.get("ETag", "").strip('"'),
        )

    def compute_sha256(self, *, key: str) -> str | None:
        from botocore.exceptions import ClientError

        try:
            response = self._client().get_object(Bucket=self._bucket, Key=key)
        except ClientError:
            return None
        digest = hashlib.sha256()
        body = response["Body"]
        for chunk in iter(lambda: body.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
        return digest.hexdigest()

    def delete_object(self, *, key: str) -> None:
        self._client().delete_object(Bucket=self._bucket, Key=key)

    def ensure_ready(self) -> None:
        from botocore.exceptions import ClientError

        client = self._client()
        try:
            client.head_bucket(Bucket=self._bucket)
        except ClientError:
            client.create_bucket(Bucket=self._bucket)


class LocalFileSystemStorage:
    """Plain disk under ``root`` (defaults to ``settings.MEDIA_ROOT /
    "files"``). Exists so a solo developer can exercise the full upload
    lifecycle without running the MinIO container — the acceptance
    criterion this class demonstrates is "switching storage backend is a
    settings change only," proven by running the same test suite against
    this class instead of ``S3CompatibleStorage``.

    ``generate_presigned_upload``/``generate_presigned_download`` cannot
    return a bucket URL — there is no bucket — so they return an
    ordinary, org-scoped app route
    (``/orgs/{org_slug}/files/{id}/local-object/``,
    ``keel.files.views.local_object_upload`` /
    ``local_object_download``), authenticated and permission-checked the
    same way as every other route in this project (``resolve_and_authorize``)
    rather than a signed token — which is fine specifically because the
    caller is already authenticated for every other step of this same
    flow."""

    def __init__(self, *, root: str = "", **_ignored_s3_options: Any) -> None:
        # **_ignored_s3_options swallows the S3-shaped OPTIONS keys
        # (endpoint_url, access_key_id, ...) that STORAGES["files"]
        # carries when S3CompatibleStorage is configured — so flipping
        # KEEL_FILES_STORAGE_BACKEND alone, without also editing OPTIONS,
        # is enough to switch (docs/storage.md).
        self._root = Path(root) if root else self._default_root()

    @staticmethod
    def _default_root() -> Path:
        from django.conf import settings

        return Path(settings.MEDIA_ROOT) / "files"

    def _path(self, key: str) -> Path:
        # ``key`` is generated by ``services._object_key`` (a uuid7, no
        # user input) — never taken from a request path segment, so this
        # is not a traversal surface.
        return self._root / key

    def _meta_path(self, key: str) -> Path:
        return self._path(key).with_suffix(self._path(key).suffix + ".meta")

    def generate_presigned_upload(
        self, *, key: str, content_type: str, organization_slug: str = "", file_upload_id: str = ""
    ) -> str:
        return f"/api/v1/orgs/{organization_slug}/files/{file_upload_id}/local-object/"

    def generate_presigned_download(
        self, *, key: str, organization_slug: str = "", file_upload_id: str = ""
    ) -> str:
        return f"/api/v1/orgs/{organization_slug}/files/{file_upload_id}/local-object/"

    def open_for_read(self, *, key: str) -> Any | None:
        """Used by ``local_object_download`` — not part of
        ``ObjectStorage``, since no other backend hands back a raw file
        object (an S3-backed download is a redirect to a presigned GET
        URL, never bytes Django streams itself)."""
        path = self._path(key)
        if not path.exists():
            return None
        return path.open("rb")

    def write(self, *, key: str, content_type: str, stream: Any) -> None:
        """Called by ``local_object_upload`` — not part of
        ``ObjectStorage``, since no other backend accepts a direct
        write (S3 objects only ever arrive via a presigned PUT the
        browser sends straight to the bucket)."""
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        with path.open("wb") as fh:
            for chunk in iter(lambda: stream.read(_CHUNK_SIZE), b""):
                digest.update(chunk)
                size += len(chunk)
                fh.write(chunk)
        self._meta_path(key).write_text(f"{content_type}\n{size}\n{digest.hexdigest()}\n")

    def _read_meta(self, key: str) -> tuple[str, int, str] | None:
        meta_path = self._meta_path(key)
        if not meta_path.exists():
            return None
        content_type, size, checksum = meta_path.read_text().splitlines()
        return content_type, int(size), checksum

    def head_object(self, *, key: str) -> ObjectMetadata | None:
        meta = self._read_meta(key)
        if meta is None or not self._path(key).exists():
            return None
        content_type, size, checksum = meta
        return ObjectMetadata(size=size, content_type=content_type, etag=checksum)

    def compute_sha256(self, *, key: str) -> str | None:
        meta = self._read_meta(key)
        return meta[2] if meta is not None else None

    def delete_object(self, *, key: str) -> None:
        self._path(key).unlink(missing_ok=True)
        self._meta_path(key).unlink(missing_ok=True)

    def ensure_ready(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)

    def _wipe(self) -> None:
        """Test-only convenience; not part of ``ObjectStorage``."""
        shutil.rmtree(self._root, ignore_errors=True)


def get_storage() -> ObjectStorage:
    """Reads ``STORAGES["files"]`` (``config/settings/base.py``) the
    same way Django's own ``django.core.files.storage.storages`` reads
    ``STORAGES["default"]`` — a separate alias because ``"default"`` is
    reserved for ``FileField``/admin uploads, which this app doesn't use
    (PRD: uploads go straight to the bucket via a presigned URL, never
    through a Django ``FileField``)."""
    from django.conf import settings
    from django.utils.module_loading import import_string

    config = settings.STORAGES["files"]
    backend_cls = import_string(config["BACKEND"])
    result: ObjectStorage = backend_cls(**config.get("OPTIONS", {}))
    return result

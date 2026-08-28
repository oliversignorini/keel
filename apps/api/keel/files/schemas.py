"""Schemas for the file-upload endpoints."""

from datetime import datetime
from typing import Literal

from ninja import Schema
from pydantic import Field

from keel.core.schemas import KeelSchema
from keel.files.models import FileUpload

# A published vocabulary, not a bare `str` — must match
# FileUpload.STATUS_CHOICES (keel/files/models.py).
FileUploadStatus = Literal["pending", "available", "failed", "expired", "deleted"]
assert set(FileUploadStatus.__args__) == {choice for choice, _ in FileUpload.STATUS_CHOICES}  # type: ignore[attr-defined]


class PresignedUploadRequest(Schema):
    filename: str = Field(max_length=255)
    content_type: str = Field(max_length=255)
    size: int = Field(ge=1)
    checksum_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$")


class FileUploadOut(KeelSchema):
    filename: str
    content_type: str
    size: int
    status: FileUploadStatus
    failure_reason: str
    created_at: datetime
    completed_at: datetime | None


class PresignedUploadOut(Schema):
    """posd#7: the create-upload route returned a bare ``dict``
    (``response={201: dict}``), which the generated TypeScript client
    types as ``void`` — the fix the review names, ``PresignedUploadOut``,
    typed as its own schema rather than folded onto ``FileUploadOut`` so
    ``upload_url`` (a one-time, expiring value, never worth persisting or
    displaying alongside a file's other fields) stays out of every other
    response that reuses ``FileUploadOut``."""

    file: FileUploadOut
    upload_url: str


class FileDownloadUrlOut(Schema):
    download_url: str

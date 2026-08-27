"""Schemas for the presigned upload endpoints (PRD §5; docs/plans/
phase-5.md 5.6; phase-10.md 10.C)."""

from datetime import datetime
from typing import Any, Literal

from ninja import Schema
from pydantic import Field

from keel.files.models import FileUpload

# api-patterns finding 14: a published vocabulary, not a bare `str` — must
# match FileUpload.STATUS_CHOICES (keel/files/models.py).
FileUploadStatus = Literal["pending", "complete"]
assert set(FileUploadStatus.__args__) == {choice for choice, _ in FileUpload.STATUS_CHOICES}  # type: ignore[attr-defined]


class PresignedUploadRequest(Schema):
    filename: str = Field(max_length=255)
    content_type: str = Field(max_length=255)
    size: int = Field(ge=1)


class FileUploadOut(Schema):
    id: str
    key: str
    content_type: str
    size: int
    status: FileUploadStatus
    created_at: datetime

    @staticmethod
    def resolve_id(obj: Any) -> str:
        return str(obj.id)

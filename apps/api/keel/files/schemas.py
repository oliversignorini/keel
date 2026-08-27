"""Schemas for the presigned upload endpoints (PRD §5; docs/plans/
phase-5.md 5.6; phase-10.md 10.C)."""

from datetime import datetime
from typing import Any

from ninja import Schema
from pydantic import Field


class PresignedUploadRequest(Schema):
    filename: str = Field(max_length=255)
    content_type: str = Field(max_length=255)
    size: int = Field(ge=1)


class FileUploadOut(Schema):
    id: str
    key: str
    content_type: str
    size: int
    status: str
    created_at: datetime

    @staticmethod
    def resolve_id(obj: Any) -> str:
        return str(obj.id)

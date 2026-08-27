"""Shape validation at the edge (PRD §4 invariant 6; phase-10.md 10.C)."""

from datetime import datetime
from typing import Any, Literal

from ninja import Schema
from pydantic import Field

from keel.jobs.models import Job

# api-patterns finding 14: a published vocabulary, not a bare `str` — must
# match Job.STATUS_CHOICES (keel/jobs/models.py). JobStep shares the same
# vocabulary (JobStep.status has no separate choices of its own).
JobStatus = Literal["queued", "running", "succeeded", "partial", "failed"]
assert set(JobStatus.__args__) == {choice for choice, _ in Job.STATUS_CHOICES}  # type: ignore[attr-defined]


class JobStepOut(Schema):
    id: str
    name: str
    ordinal: int
    status: JobStatus
    output_ref: str
    started_at: datetime | None
    finished_at: datetime | None
    error: str

    @staticmethod
    def resolve_id(obj: Any) -> str:
        return str(obj.id)


class JobOut(Schema):
    id: str
    type: str
    status: JobStatus
    params: dict[str, Any]
    result_ref: str
    error: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    steps: list[JobStepOut]

    @staticmethod
    def resolve_id(obj: Any) -> str:
        return str(obj.id)

    @staticmethod
    def resolve_steps(obj: Any) -> list[Any]:
        return list(obj.steps.all())


class JobCreateIn(Schema):
    type: str
    params: dict[str, Any] = Field(default_factory=dict)

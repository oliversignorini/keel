"""Reads over ``Job`` (PRD §4 invariant 1: "selectors query and return")."""

from __future__ import annotations

from typing import Any

from django.db.models import Prefetch

from keel.jobs.models import Job, JobStep


def list_jobs_for_organization(organization: Any, status: str | None = None) -> Any:
    """``JobOut.resolve_steps`` (``keel/jobs/schemas.py``) reads
    ``obj.steps.all()`` for every job — without this prefetch that is one
    extra query per row on ``GET .../jobs/``."""
    queryset = (
        Job.objects.for_organization(organization)
        .prefetch_related(Prefetch("steps", queryset=JobStep.objects.order_by("ordinal")))
        .order_by("-created_at")
    )
    if status:
        queryset = queryset.filter(status=status)
    return queryset

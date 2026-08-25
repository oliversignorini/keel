"""Reads over ``Job`` (PRD §4 invariant 1: "selectors query and return")."""

from __future__ import annotations

from typing import Any

from keel.jobs.models import Job


def list_jobs_for_organization(organization: Any, status: str | None = None) -> Any:
    queryset = Job.objects.for_organization(organization).order_by("-created_at")
    if status:
        queryset = queryset.filter(status=status)
    return queryset

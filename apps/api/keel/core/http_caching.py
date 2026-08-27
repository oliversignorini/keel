"""Conditional-request headers for Reference Data Holders (api-patterns
finding 13) — long-lived, read-only collections like ``GET /api/v1/plans/``
and ``GET /api/v1/permissions/``. The pattern's own caveat applies: this
saves bandwidth on a repeat request, not the query itself — callers still
run their lookup, this only decides what headers ride along with it.
"""

import hashlib
from typing import Any

from django.http import HttpResponse

CACHE_CONTROL_REFERENCE_DATA = "public, max-age=300"


def compute_etag(*parts: Any) -> str:
    """A weak content hash over ``parts`` — callers pass whatever
    identifies the current representation (an aggregate max-updated-at
    and count, a sorted list of codes), not the serialised body itself,
    so this stays cheap for a collection endpoint."""
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()
    return f'"{digest}"'


def set_reference_data_cache_headers(response: HttpResponse, *etag_parts: Any) -> None:
    """Sets ``Cache-Control`` and ``ETag`` on ``response``. No server-side
    conditional-GET short-circuit here — that's a separate decision
    (api-patterns finding 13 is explicit: don't stack it with this one) —
    this is the client/proxy-cacheability half only."""
    response["Cache-Control"] = CACHE_CONTROL_REFERENCE_DATA
    response["ETag"] = compute_etag(*etag_parts)

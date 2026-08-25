"""Cursor pagination (PRD §7 conventions): ``{ results, next, previous }``.

Subclasses DRF's own ``CursorPagination`` rather than reimplementing it —
DRF's cursor already encodes a within-tie offset alongside the ordering
value specifically so a page boundary landing inside a run of equal sort
values neither skips nor repeats rows, which is the property a
hand-rolled "cursor = last id seen" implementation gets wrong.

That guarantee only holds if ``ordering`` is a *total* order. A bare
non-unique sort key (``ordering = "rank"`` with several rows sharing a
rank) has no deterministic tiebreak between requests, and Postgres is
free to return ties in a different relative order on each query — pages
then silently skip or repeat rows, which is exactly the bug this class
exists to avoid. So the default here ends in ``"id"`` as a tiebreaker,
and any subclass overriding ``ordering`` must do the same — end the tuple
in a column guaranteed unique.
"""

from rest_framework.pagination import CursorPagination as DRFCursorPagination


class CursorPagination(DRFCursorPagination):
    page_size = 25
    ordering = ("-created_at", "id")
    cursor_query_param = "cursor"
    page_size_query_param = "limit"

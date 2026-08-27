"""Proves ``keel.core.ninja_pagination.CursorPaginator`` carries over the
same tie-safe guarantee as the DRF cursor paginator it was ported from
(see ``keel/core/ninja_pagination.py``'s module docstring and
``keel/core/tests/test_pagination.py`` for the DRF-side proof this was
ported from). ADR 0001 / phase-10.md 10.A: "a hand-rolled 'cursor = last
id seen' will pass a naive test and fail this one" — so this uses ≥60
rows sharing a single tied sort value and walks every page end to end,
which a naive implementation cannot survive.

Uses an ``isolate_apps`` fixture model, the same pattern
``test_pagination.py`` uses, rather than a real app's model — ``keel.core``
must not import ``keel.organizations`` or any other app
(the "keel.core does not import keel.organizations" import-linter
contract, and its spirit extends to every other app for the same reason).
"""

from urllib.parse import parse_qs, urlparse

import pytest
from django.db import connection, models
from django.test import RequestFactory
from django.test.utils import isolate_apps

from keel.core.ninja_pagination import CursorPaginator


def _paginate_all(paginator_cls, queryset, page_size):
    factory = RequestFactory()
    seen = []
    cursor = None
    while True:
        paginator = paginator_cls()
        paginator.page_size = page_size
        request = factory.get("/fake/things/", {"cursor": cursor} if cursor else {})
        page = paginator.paginate_queryset(queryset, request)
        seen.extend(row.id for row in page)
        response = paginator.get_paginated_response([row.id for row in page])
        next_link = response["next"]
        if not next_link:
            break
        cursor = parse_qs(urlparse(next_link).query)["cursor"][0]
    return seen


@pytest.mark.django_db(transaction=True)
@isolate_apps("keel.core")
def test_ninja_cursor_pagination_across_sixty_tied_rows() -> None:
    class Row(models.Model):
        rank = models.IntegerField()

        class Meta:
            app_label = "core"

        def __str__(self) -> str:
            return f"Row(rank={self.rank})"

    with connection.schema_editor() as editor:
        editor.create_model(Row)
    try:
        expected_ids = set()
        for _ in range(65):
            # A single tied rank — the run a naive "cursor = last id
            # seen" implementation cannot survive without skipping or
            # repeating rows (phase-10.md 10.A).
            expected_ids.add(Row.objects.create(rank=1).id)  # type: ignore[attr-defined]

        class RowCursorPaginator(CursorPaginator):
            ordering = ("rank", "id")

        row_queryset = Row.objects.all()  # type: ignore[attr-defined]
        seen = _paginate_all(RowCursorPaginator, row_queryset, page_size=7)

        assert len(seen) == len(expected_ids), "pagination skipped or repeated rows"
        assert set(seen) == expected_ids
        assert len(seen) == len(set(seen)), "pagination repeated a row"
    finally:
        with connection.schema_editor() as editor:
            editor.delete_model(Row)


@pytest.mark.django_db(transaction=True)
@isolate_apps("keel.core")
def test_ninja_cursor_pagination_response_envelope_shape() -> None:
    class EnvelopeRow(models.Model):
        rank = models.IntegerField()

        class Meta:
            app_label = "core"

        def __str__(self) -> str:
            return f"EnvelopeRow(rank={self.rank})"

    with connection.schema_editor() as editor:
        editor.create_model(EnvelopeRow)
    try:
        for _ in range(5):
            EnvelopeRow.objects.create(rank=1)  # type: ignore[attr-defined]

        class EnvelopeCursorPaginator(CursorPaginator):
            ordering = ("rank", "id")
            page_size = 2

        paginator = EnvelopeCursorPaginator()
        request = RequestFactory().get("/fake/things/")
        envelope_queryset = EnvelopeRow.objects.all()  # type: ignore[attr-defined]
        page = paginator.paginate_queryset(envelope_queryset, request)
        response = paginator.get_paginated_response([row.id for row in page])

        assert set(response.keys()) == {"results", "next", "previous"}
        assert response["previous"] is None
        assert response["next"] is not None
    finally:
        with connection.schema_editor() as editor:
            editor.delete_model(EnvelopeRow)

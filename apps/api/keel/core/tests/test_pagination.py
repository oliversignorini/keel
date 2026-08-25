"""Cursor pagination must stay stable across a run of equal sort values —
a page boundary landing inside such a run is the classic silent-skip bug
this test exists to catch."""

from urllib.parse import parse_qs, urlparse

import pytest
from django.db import connection, models
from django.test.utils import isolate_apps
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from keel.core.pagination import CursorPagination


def _paginate_all(paginator_cls, queryset, page_size):
    """Walk every page via next-links, returning the ids seen in order."""
    factory = APIRequestFactory()
    seen = []
    cursor = None
    while True:
        paginator = paginator_cls()
        paginator.page_size = page_size
        django_request = factory.get("/fake/things/", {"cursor": cursor} if cursor else {})
        request = Request(django_request)
        page = paginator.paginate_queryset(queryset, request)
        seen.extend(row.id for row in page)
        next_link = paginator.get_next_link()
        if not next_link:
            break
        cursor = parse_qs(urlparse(next_link).query)["cursor"][0]
    return seen


@pytest.mark.django_db(transaction=True)
@isolate_apps("keel.core")
def test_cursor_pagination_across_a_run_of_equal_sort_values() -> None:
    class Row(models.Model):
        rank = models.IntegerField()

        class Meta:
            app_label = "core"

    with connection.schema_editor() as editor:
        editor.create_model(Row)
    try:
        expected_ids = set()
        for _ in range(4):
            expected_ids.add(Row.objects.create(rank=1).id)
        for _ in range(4):
            expected_ids.add(Row.objects.create(rank=1).id)  # same rank, second batch
        for _ in range(4):
            expected_ids.add(Row.objects.create(rank=2).id)

        class RowCursorPagination(CursorPagination):
            # "rank" alone is non-unique (several rows share rank=1); "id"
            # is the tiebreaker that makes the ordering total, per
            # keel.core.pagination's module docstring.
            ordering = ("rank", "id")

        seen = _paginate_all(RowCursorPagination, Row.objects.all(), page_size=3)

        assert len(seen) == len(expected_ids), "pagination skipped or repeated rows"
        assert set(seen) == expected_ids
        assert len(seen) == len(set(seen)), "pagination repeated a row"
    finally:
        with connection.schema_editor() as editor:
            editor.delete_model(Row)


@pytest.mark.django_db(transaction=True)
@isolate_apps("keel.core")
def test_cursor_pagination_response_envelope_shape() -> None:
    class EnvelopeRow(models.Model):
        rank = models.IntegerField()

        class Meta:
            app_label = "core"

    with connection.schema_editor() as editor:
        editor.create_model(EnvelopeRow)
    try:
        for _ in range(5):
            EnvelopeRow.objects.create(rank=1)

        class EnvelopeCursorPagination(CursorPagination):
            ordering = "rank"
            page_size = 2

        paginator = EnvelopeCursorPagination()
        request = Request(APIRequestFactory().get("/fake/things/"))
        page = paginator.paginate_queryset(EnvelopeRow.objects.all(), request)
        response = paginator.get_paginated_response([row.id for row in page])

        assert set(response.data.keys()) == {"results", "next", "previous"}
        assert response.data["previous"] is None
        assert response.data["next"] is not None
    finally:
        with connection.schema_editor() as editor:
            editor.delete_model(EnvelopeRow)

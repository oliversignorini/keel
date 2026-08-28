"""Proves ``keel.core.pagination.CursorPaginator`` carries the tie-safe
guarantee its module docstring describes (see ``keel/core/pagination.py``).
ADR 0001: "a hand-rolled 'cursor = last id seen' will
pass a naive test and fail this one" — so this uses ≥60 rows sharing a
single tied sort value and walks every page end to end, which a naive
implementation cannot survive.

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

from keel.core.pagination import CursorPaginator, InvalidPagination, _positive_int


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
            # repeating rows.
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


# --- The rest of the ported surface --------------------------------------
#
# The two tests above prove the guarantee that matters (no skipped or
# repeated row across a tie). These cover the branches that guarantee
# depends on but that a forward-only walk over a single tied value never
# reaches: backward traversal, the position filter for a *mixed* ordering,
# the client-supplied `limit`, and the malformed-cursor path.


def _cursor_of(link):
    return parse_qs(urlparse(link).query)["cursor"][0]


def _page(paginator_cls, queryset, page_size, query=None):
    """One page: returns ``(ids, envelope)``."""
    paginator = paginator_cls()
    paginator.page_size = page_size
    request = RequestFactory().get("/fake/things/", query or {})
    rows = paginator.paginate_queryset(queryset, request)
    ids = [row.id for row in rows]
    return ids, paginator.get_paginated_response(ids)


@pytest.mark.django_db(transaction=True)
@isolate_apps("keel.core")
def test_walking_forward_then_backward_returns_the_same_rows() -> None:
    """Mixed sort values, so the cursor actually carries a ``position``
    and the ``__gt`` / ``__lt`` filter runs — then the previous-links are
    walked back to the start, which is the only path through the
    reverse-ordering branch."""

    class MixedRow(models.Model):
        rank = models.IntegerField()

        class Meta:
            app_label = "core"

        def __str__(self) -> str:
            return f"MixedRow(rank={self.rank})"

    with connection.schema_editor() as editor:
        editor.create_model(MixedRow)
    try:
        for rank in range(12):
            # Two rows per rank: enough ties to need the within-tie
            # offset, enough distinct values to need the position filter.
            MixedRow.objects.create(rank=rank)  # type: ignore[attr-defined]
            MixedRow.objects.create(rank=rank)  # type: ignore[attr-defined]

        class MixedPaginator(CursorPaginator):
            ordering = ("rank", "id")

        queryset = MixedRow.objects.all()  # type: ignore[attr-defined]

        forward_pages = []
        query: dict = {}
        while True:
            ids, envelope = _page(MixedPaginator, queryset, 5, query)
            forward_pages.append(ids)
            if not envelope["next"]:
                break
            query = {"cursor": _cursor_of(envelope["next"])}

        flat = [row_id for page in forward_pages for row_id in page]
        assert len(flat) == 24
        assert len(set(flat)) == 24

        # Walk back from the last page. Every previous-link must hand back
        # rows already seen, in the same order, never a fresh row.
        backward_pages = []
        _, envelope = _page(MixedPaginator, queryset, 5, query)
        while envelope["previous"]:
            ids, envelope = _page(
                MixedPaginator, queryset, 5, {"cursor": _cursor_of(envelope["previous"])}
            )
            backward_pages.append(ids)

        # backward_pages come back last-page-first; re-reverse them and
        # the result must line up with the forward walk exactly.
        walked_back = [row_id for page in reversed(backward_pages) for row_id in page]
        assert set(walked_back) <= set(flat)
        assert walked_back == sorted(walked_back, key=flat.index)
        assert flat[0] in walked_back, "walking back never reached the first page"
    finally:
        with connection.schema_editor() as editor:
            editor.delete_model(MixedRow)


@pytest.mark.django_db(transaction=True)
@isolate_apps("keel.core")
def test_limit_query_param_overrides_the_default_page_size() -> None:
    class LimitRow(models.Model):
        rank = models.IntegerField()

        class Meta:
            app_label = "core"

        def __str__(self) -> str:
            return f"LimitRow(rank={self.rank})"

    with connection.schema_editor() as editor:
        editor.create_model(LimitRow)
    try:
        for rank in range(10):
            LimitRow.objects.create(rank=rank)  # type: ignore[attr-defined]

        class LimitPaginator(CursorPaginator):
            ordering = ("rank", "id")

        queryset = LimitRow.objects.all()  # type: ignore[attr-defined]

        ids, _ = _page(LimitPaginator, queryset, 5, {"limit": "3"})
        assert len(ids) == 3

        # A junk or non-positive limit is the client's error, not a silent
        # fallback (api-patterns finding 8) — same 422 the malformed-cursor
        # test below asserts, and the same code.
        for bad_limit in ("not-a-number", "0", "-1"):
            paginator = LimitPaginator()
            paginator.page_size = 5
            request = RequestFactory().get("/fake/things/", {"limit": bad_limit})
            with pytest.raises(InvalidPagination) as excinfo:
                paginator.paginate_queryset(queryset, request)
            assert excinfo.value.status_code == 422
            assert excinfo.value.code == "invalid_pagination"
    finally:
        with connection.schema_editor() as editor:
            editor.delete_model(LimitRow)


@pytest.mark.django_db(transaction=True)
@isolate_apps("keel.core")
def test_limit_above_the_maximum_is_capped_not_rejected() -> None:
    """Unlike a malformed limit, an *oversized* one is still a valid
    request — it is simply capped at ``max_page_size`` (api-patterns
    finding 9 / ddia finding 26) rather than answering the full table."""

    class CappedRow(models.Model):
        rank = models.IntegerField()

        class Meta:
            app_label = "core"

        def __str__(self) -> str:
            return f"CappedRow(rank={self.rank})"

    with connection.schema_editor() as editor:
        editor.create_model(CappedRow)
    try:
        for rank in range(5):
            CappedRow.objects.create(rank=rank)  # type: ignore[attr-defined]

        class CappedPaginator(CursorPaginator):
            ordering = ("rank", "id")
            max_page_size = 3

        queryset = CappedRow.objects.all()  # type: ignore[attr-defined]
        ids, _ = _page(CappedPaginator, queryset, 5, {"limit": "1000000"})
        assert len(ids) == 3
    finally:
        with connection.schema_editor() as editor:
            editor.delete_model(CappedRow)


@pytest.mark.django_db(transaction=True)
@isolate_apps("keel.core")
def test_a_single_string_ordering_is_accepted() -> None:
    """``ordering`` is normally a tuple, but a lone string is the shape a
    caller most naturally reaches for and is normalised rather than
    silently iterated character by character."""

    class StringOrderRow(models.Model):
        rank = models.IntegerField()

        class Meta:
            app_label = "core"

        def __str__(self) -> str:
            return f"StringOrderRow(rank={self.rank})"

    with connection.schema_editor() as editor:
        editor.create_model(StringOrderRow)
    try:
        for rank in range(3):
            StringOrderRow.objects.create(rank=rank)  # type: ignore[attr-defined]

        class StringOrderPaginator(CursorPaginator):
            ordering = "rank"  # type: ignore[assignment]

        queryset = StringOrderRow.objects.all()  # type: ignore[attr-defined]
        ids, _ = _page(StringOrderPaginator, queryset, 5)

        assert len(ids) == 3
    finally:
        with connection.schema_editor() as editor:
            editor.delete_model(StringOrderRow)


def test_a_malformed_cursor_is_422_invalid_pagination() -> None:
    """A tampered or truncated cursor is the client's error, not a 500 —
    PRD §7's 422 row (``keel.core.exceptions.UnprocessableEntity``), and
    the same code a malformed ``limit`` raises (api-patterns finding 8)."""
    paginator = CursorPaginator()
    request = RequestFactory().get("/fake/things/", {"cursor": "bz1ub3QtYS1udW1iZXI="})

    with pytest.raises(InvalidPagination) as excinfo:
        paginator._decode_cursor(request)

    assert excinfo.value.status_code == 422
    assert excinfo.value.code == "invalid_pagination"


def test_position_is_read_from_a_dict_row_as_well_as_a_model_instance() -> None:
    """``paginate()`` is always handed ORM instances, but the ported
    algorithm supports ``.values()`` rows too and the branch would
    otherwise rot unnoticed."""
    paginator = CursorPaginator()
    paginator.ordering = ("-created_at", "id")

    assert paginator._position_from_instance({"created_at": "2026-01-01"}) == "2026-01-01"


def test_a_negative_page_size_is_rejected() -> None:
    with pytest.raises(ValueError):
        _positive_int("-1")


def test_positive_int_with_no_cutoff_returns_the_value_unchanged() -> None:
    """Every production call site now passes a ``cutoff`` (page size caps
    at ``max_page_size``, the cursor offset caps at ``offset_cutoff``) —
    this covers the no-cutoff branch directly so it isn't dead code."""
    assert _positive_int("7") == 7


@pytest.mark.django_db(transaction=True)
@isolate_apps("keel.core")
def test_walking_backward_through_a_fully_tied_run() -> None:
    """The tie-safety guarantee has to hold in both directions: the
    within-tie offset is carried on a reverse cursor too, and a backward
    walk over one long run of equal values is where that bookkeeping is
    easiest to get wrong."""

    class TiedBackRow(models.Model):
        rank = models.IntegerField()

        class Meta:
            app_label = "core"

        def __str__(self) -> str:
            return f"TiedBackRow(rank={self.rank})"

    with connection.schema_editor() as editor:
        editor.create_model(TiedBackRow)
    try:
        for _ in range(30):
            TiedBackRow.objects.create(rank=1)  # type: ignore[attr-defined]

        class TiedBackPaginator(CursorPaginator):
            ordering = ("rank", "id")

        queryset = TiedBackRow.objects.all()  # type: ignore[attr-defined]

        forward: list[list[int]] = []
        query: dict = {}
        while True:
            ids, envelope = _page(TiedBackPaginator, queryset, 4, query)
            forward.append(ids)
            if not envelope["next"]:
                break
            query = {"cursor": _cursor_of(envelope["next"])}

        backward: list[list[int]] = []
        _, envelope = _page(TiedBackPaginator, queryset, 4, query)
        while envelope["previous"]:
            ids, envelope = _page(
                TiedBackPaginator, queryset, 4, {"cursor": _cursor_of(envelope["previous"])}
            )
            backward.append(ids)

        flat_forward = [row_id for page in forward for row_id in page]
        flat_backward = [row_id for page in reversed(backward) for row_id in page]

        assert len(flat_forward) == 30
        assert len(set(flat_backward)) == len(flat_backward), "walking back repeated a row"
        assert flat_backward == sorted(flat_backward, key=flat_forward.index)
        assert flat_forward[0] in flat_backward, "walking back never reached the first row"
    finally:
        with connection.schema_editor() as editor:
            editor.delete_model(TiedBackRow)


@pytest.mark.django_db(transaction=True)
@isolate_apps("keel.core")
def test_a_cursor_whose_rows_have_all_been_deleted_still_answers() -> None:
    """A cursor is a bookmark into data that can change underneath it.
    Every row vanishing between two requests must produce an empty page
    with usable links, not a crash — in both directions."""

    class VanishingRow(models.Model):
        rank = models.IntegerField()

        class Meta:
            app_label = "core"

        def __str__(self) -> str:
            return f"VanishingRow(rank={self.rank})"

    with connection.schema_editor() as editor:
        editor.create_model(VanishingRow)
    try:
        for rank in range(9):
            VanishingRow.objects.create(rank=rank)  # type: ignore[attr-defined]

        class VanishingPaginator(CursorPaginator):
            ordering = ("rank", "id")

        queryset = VanishingRow.objects.all()  # type: ignore[attr-defined]

        _, first = _page(VanishingPaginator, queryset, 3)
        forward_cursor = _cursor_of(first["next"])
        _, second = _page(VanishingPaginator, queryset, 3, {"cursor": forward_cursor})
        reverse_cursor = _cursor_of(second["previous"])

        VanishingRow.objects.all().delete()  # type: ignore[attr-defined]

        ids, envelope = _page(VanishingPaginator, queryset, 3, {"cursor": forward_cursor})
        assert ids == []
        assert envelope["previous"] is not None

        ids, envelope = _page(VanishingPaginator, queryset, 3, {"cursor": reverse_cursor})
        assert ids == []
        assert envelope["next"] is not None
    finally:
        with connection.schema_editor() as editor:
            editor.delete_model(VanishingRow)

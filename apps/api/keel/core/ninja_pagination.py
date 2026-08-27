"""Cursor pagination for Ninja routes (PRD §7 conventions): ``{ results,
next, previous }``.

Ported from ``rest_framework.pagination.CursorPagination`` line for line,
not reimplemented from scratch — see ``keel/core/pagination.py``'s
docstring (kept for the DRF views that still exist during the migration)
for why a hand-rolled "cursor = last id seen" approach is wrong: the
within-tie offset encoded alongside the ordering value is what lets a page
boundary land inside a run of equal sort values without skipping or
repeating rows. Django Ninja ships no cursor paginator at all, so this
exists to carry that guarantee over unchanged, verified by
``keel/core/tests/test_ninja_pagination.py``'s ≥60-tied-row test.

Operates on a plain Django ``HttpRequest`` and a queryset — no DRF types
involved — so it has no dependency on ``rest_framework`` and survives its
removal in stage 10.E.
"""

from base64 import b64decode, b64encode
from collections import namedtuple
from collections.abc import Sequence
from typing import Any
from urllib import parse

from django.http import HttpRequest

from keel.core.exceptions import UnprocessableEntity

Cursor = namedtuple("Cursor", ["offset", "reverse", "position"])


def _positive_int(value: Any, strict: bool = False, cutoff: int | None = None) -> int:
    result = int(value)
    if result < 0 or (result == 0 and strict):
        raise ValueError("Expected a positive integer.")
    if cutoff:
        return min(result, cutoff)
    return result


def _reverse_ordering(ordering: Sequence[str]) -> tuple[str, ...]:
    def invert(item: str) -> str:
        return item[1:] if item.startswith("-") else "-" + item

    return tuple(invert(item) for item in ordering)


def _replace_query_param(url: str, key: str, val: Any) -> str:
    scheme, netloc, path, query, fragment = parse.urlsplit(url)
    query_dict = parse.parse_qs(query, keep_blank_values=True)
    query_dict[key] = [str(val)]
    query = parse.urlencode(sorted(query_dict.items()), doseq=True)
    return parse.urlunsplit((scheme, netloc, path, query, fragment))


def _remove_query_param(url: str, key: str) -> str:
    scheme, netloc, path, query, fragment = parse.urlsplit(url)
    query_dict = parse.parse_qs(query, keep_blank_values=True)
    query_dict.pop(key, None)
    query = parse.urlencode(sorted(query_dict.items()), doseq=True)
    return parse.urlunsplit((scheme, netloc, path, query, fragment))


class InvalidCursor(UnprocessableEntity):
    default_code = "invalid_cursor"
    default_message = "Invalid cursor"


class CursorPaginator:
    """Instantiate per request (mirrors DRF's per-request pagination
    instance — ``self.cursor``/``self.page`` etc. are request-local
    state, not class state)."""

    cursor_query_param = "cursor"
    page_size_query_param = "limit"
    page_size = 25
    ordering: Sequence[str] = ("-created_at", "id")
    offset_cutoff = 1000

    def __init__(self) -> None:
        self.cursor: Cursor | None = None
        self.page: list[Any] = []
        self.has_next = False
        self.has_previous = False
        self.next_position: str | None = None
        self.previous_position: str | None = None

    def paginate_queryset(self, queryset: Any, request: HttpRequest) -> list[Any]:
        self.request = request
        self.page_size = self._get_page_size(request)
        self.base_url = request.build_absolute_uri()
        self.ordering = self._get_ordering()

        self.cursor = self._decode_cursor(request)
        cursor = self.cursor
        current_position: str | None
        if cursor is None:
            offset, reverse, current_position = 0, False, None
        else:
            offset, reverse, current_position = cursor

        if reverse:
            queryset = queryset.order_by(*_reverse_ordering(self.ordering))
        else:
            queryset = queryset.order_by(*self.ordering)

        if current_position is not None and cursor is not None:
            order = self.ordering[0]
            is_reversed = order.startswith("-")
            order_attr = order.lstrip("-")

            if cursor.reverse != is_reversed:
                kwargs = {order_attr + "__lt": current_position}
            else:
                kwargs = {order_attr + "__gt": current_position}
            queryset = queryset.filter(**kwargs)

        results = list(queryset[offset : offset + self.page_size + 1])
        self.page = list(results[: self.page_size])

        if len(results) > len(self.page):
            has_following_position = True
            following_position = self._position_from_instance(results[-1])
        else:
            has_following_position = False
            following_position = None

        if reverse:
            self.page = list(reversed(self.page))
            self.has_next = (current_position is not None) or (offset > 0)
            self.has_previous = has_following_position
            if self.has_next:
                self.next_position = current_position
            if self.has_previous:
                self.previous_position = following_position
        else:
            self.has_next = has_following_position
            self.has_previous = (current_position is not None) or (offset > 0)
            if self.has_next:
                self.next_position = following_position
            if self.has_previous:
                self.previous_position = current_position

        return self.page

    def get_paginated_response(self, data: Any) -> dict[str, Any]:
        return {
            "results": data,
            "next": self._next_link(),
            "previous": self._previous_link(),
        }

    def _get_page_size(self, request: HttpRequest) -> int:
        if self.page_size_query_param:
            raw = request.GET.get(self.page_size_query_param)
            if raw is not None:
                try:
                    return _positive_int(raw, strict=True)
                except ValueError:
                    pass
        return self.page_size

    def _get_ordering(self) -> tuple[str, ...]:
        ordering = self.ordering
        assert ordering is not None
        assert "__" not in "".join(ordering)
        if isinstance(ordering, str):
            return (ordering,)
        return tuple(ordering)

    def _decode_cursor(self, request: HttpRequest) -> Cursor | None:
        encoded = request.GET.get(self.cursor_query_param)
        if encoded is None:
            return None
        try:
            querystring = b64decode(encoded.encode("ascii")).decode("ascii")
            tokens = parse.parse_qs(querystring, keep_blank_values=True)

            offset = _positive_int(tokens.get("o", ["0"])[0], cutoff=self.offset_cutoff)
            reverse = bool(int(tokens.get("r", ["0"])[0]))
            position = tokens.get("p", [None])[0]
        except (TypeError, ValueError) as exc:
            raise InvalidCursor() from exc
        return Cursor(offset=offset, reverse=reverse, position=position)

    def _encode_cursor(self, cursor: Cursor) -> str:
        tokens = {}
        if cursor.offset != 0:
            tokens["o"] = str(cursor.offset)
        if cursor.reverse:
            tokens["r"] = "1"
        if cursor.position is not None:
            tokens["p"] = cursor.position
        querystring = parse.urlencode(tokens, doseq=True)
        encoded = b64encode(querystring.encode("ascii")).decode("ascii")
        return _replace_query_param(self.base_url, self.cursor_query_param, encoded)

    def _position_from_instance(self, instance: Any) -> str:
        field_name = self.ordering[0].lstrip("-")
        if isinstance(instance, dict):
            attr = instance[field_name]
        else:
            attr = getattr(instance, field_name)
        return str(attr)

    def _next_link(self) -> str | None:
        if not self.has_next:
            return None

        cursor = self.cursor
        compare: str | None
        if self.page and cursor and cursor.reverse and cursor.offset != 0:
            compare = self._position_from_instance(self.page[-1])
        else:
            compare = self.next_position
        offset = 0
        position = compare

        has_item_with_unique_position = False
        for item in reversed(self.page):
            position = self._position_from_instance(item)
            if position != compare:
                has_item_with_unique_position = True
                break
            compare = position
            offset += 1

        if self.page and not has_item_with_unique_position:
            if not self.has_previous:
                offset = self.page_size
                position = None
            elif cursor is not None and cursor.reverse:
                offset = 0
                position = self.previous_position
            elif cursor is not None:
                offset = cursor.offset + self.page_size
                position = self.previous_position

        if not self.page:
            position = self.next_position

        return self._encode_cursor(Cursor(offset=offset, reverse=False, position=position))

    def _previous_link(self) -> str | None:
        if not self.has_previous:
            return None

        cursor = self.cursor
        compare: str | None
        if self.page and cursor and not cursor.reverse and cursor.offset != 0:
            compare = self._position_from_instance(self.page[0])
        else:
            compare = self.previous_position
        offset = 0
        position = compare

        has_item_with_unique_position = False
        for item in self.page:
            position = self._position_from_instance(item)
            if position != compare:
                has_item_with_unique_position = True
                break
            compare = position
            offset += 1

        if self.page and not has_item_with_unique_position:
            if not self.has_next:
                offset = self.page_size
                position = None
            elif cursor is not None and cursor.reverse:
                offset = cursor.offset + self.page_size
                position = self.next_position
            elif cursor is not None:
                offset = 0
                position = self.next_position

        if not self.page:
            position = self.previous_position

        return self._encode_cursor(Cursor(offset=offset, reverse=True, position=position))


def paginate(request: HttpRequest, queryset: Any, serialize: Any) -> dict[str, Any]:
    """Paginate ``queryset`` per the request's ``cursor``/``limit`` params
    and serialize each row with ``serialize`` (a callable, e.g. a Ninja
    ``Schema.from_orm`` or plain dict-builder)."""
    paginator = CursorPaginator()
    page = paginator.paginate_queryset(queryset, request)
    return paginator.get_paginated_response([serialize(obj) for obj in page])

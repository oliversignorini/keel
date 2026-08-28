"""Shared read helpers every app's ``selectors.py`` builds on (PRD §4
invariant 1).

``get_scoped_or_404`` replaces the twelve copy-pasted ``_get_X_or_404``
functions that each filtered an already-organisation-scoped queryset by
``pk``, called ``.first()``, and raised ``Http404`` on ``None`` (posd#10).
Callers pass a queryset already narrowed to one organisation (typically
via ``for_organization`` or an app selector) — this helper only adds the
pk lookup and the 404, it never scopes by tenant itself.
"""

from django.db.models import Model, QuerySet
from django.http import Http404


def get_scoped_or_404[ModelT: Model](queryset: QuerySet[ModelT], pk: object) -> ModelT:
    obj = queryset.filter(pk=pk).first()
    if obj is None:
        raise Http404
    return obj

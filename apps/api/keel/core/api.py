"""The single ``NinjaAPI`` instance every migrated app mounts a router on
(PRD phase-10.md 10.A/10.D). One instance, not one per app, so the merged
OpenAPI document (``scripts/merge_openapi.py``) has one schema to read.

CSRF: django-ninja only auto-enforces CSRF for its built-in
``APIKeyCookie``-style auth classes (``csrf=True`` there defaults on);
plain callables like ``keel.core.auth.session_auth`` get no
automatic check at all. That auth callable performs its own CSRF check
instead and answers 401, not 403, on failure (see that module's
docstring) — Ninja's built-in mechanism answers 403 instead, which would
disclose that an unauthenticated request reached a real route.

OpenAPI version: django-ninja 1.6.3 hard-codes ``"openapi": "3.1.0"`` in
``ninja.openapi.schema.OpenAPISchema.__init__`` with no setting to
override it, and its generated component schemas use real 3.1 / JSON
Schema 2020-12 shapes (nullable-via-``type`` arrays, ``prefixItems``,
etc.), not just the version string — allauth headless emits actual 3.0.3.
Stage 10.D deals with this for real (see its notes in
``docs/plans/phase-10.md`` and the phase-10 report); this module is not
the place to paper over it with a string replacement that would leave
the component schemas in the wrong dialect underneath a lying version
number.
"""

from ninja import NinjaAPI

from keel.core import error_handlers

api = NinjaAPI(
    title="Keel API",
    version="1.0.0",
    description="Keel — Django + Next.js SaaS template.",
)

error_handlers.register(api)

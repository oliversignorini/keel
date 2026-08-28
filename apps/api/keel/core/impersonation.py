"""Impersonation session state and the shared restriction primitive (PRD
§6 "Impersonation"; docs/plans/phase-8.md 8.3).

The session, not a request header, is the source of truth: staff starts
impersonation from Django admin, which logs the browser session in as
the target user (``django.contrib.auth.login``) while stashing the
staff member's own id under ``IMPERSONATOR_SESSION_KEY``. Every request
from then on authenticates as the target user — permissions, org
membership, everything — with the impersonator recoverable from the
session alone. This is the same shape ``django.contrib.auth`` already
uses for "log in as", not a bespoke auth path.

``current_impersonator_id()`` reads a contextvar rather than a request:
``keel.core.middleware.ImpersonationMiddleware`` sets it once per request
so code that doesn't have (and shouldn't need) the request object —
signal receivers on third-party models, most notably
``keel.accounts.mfa_guard`` — can still ask "is the current request
impersonating?" without threading a request through library internals
this project doesn't own.
"""

from contextvars import ContextVar
from typing import Any

from django.contrib.auth import login
from django.http import HttpRequest

from keel.core.exceptions import PermissionDeniedWithReason

IMPERSONATOR_SESSION_KEY = "impersonator_id"

_current_impersonator_id: ContextVar[Any] = ContextVar("current_impersonator_id", default=None)


class ImpersonationRestricted(PermissionDeniedWithReason):
    default_code = "impersonation_restricted"
    default_message = "This action is not available in an impersonated session."


def forbid_when_impersonating(impersonator: Any, action: str) -> None:
    """Called from a service (or an equivalent enforcement point for a
    third-party-owned flow — see ``keel.notifications.adapter`` and
    ``keel.accounts.mfa_guard``) with whatever the caller resolved as
    "is this session impersonating". Raises unconditionally when it is —
    the four restrictions (PRD §6) apply to every impersonated session,
    there is no partial-permission variant."""
    if impersonator is not None:
        raise ImpersonationRestricted(
            code="impersonation_restricted",
            message=f"Impersonated sessions cannot {action}.",
            denial={"action": action},
        )


def get_impersonator_id(request: HttpRequest) -> Any:
    return request.session.get(IMPERSONATOR_SESSION_KEY)


def get_current_impersonator_id() -> Any:
    """The contextvar ``keel.core.middleware.ImpersonationMiddleware``
    publishes per request — for code that has no ``request`` to read
    (signal receivers on third-party models; see
    ``keel.accounts.mfa_guard``)."""
    return _current_impersonator_id.get()


def is_impersonating(request: HttpRequest) -> bool:
    return get_impersonator_id(request) is not None


def start_impersonation(request: HttpRequest, *, impersonator: Any, target: Any) -> None:
    """Logs ``request`` in as ``target`` and records ``impersonator`` in
    the session. The audit row (``impersonation.start``, carrying both
    users) is written by the caller — ``keel.accounts.admin``'s
    "Impersonate" action — which has the request's ip/user_agent this
    module deliberately doesn't take."""
    # str(): the session backend JSON-serialises its data, and User.pk is
    # a UUID (keel/core/ids.py's uuid7), which json.dumps can't encode.
    request.session[IMPERSONATOR_SESSION_KEY] = str(impersonator.pk)
    login(request, target, backend="django.contrib.auth.backends.ModelBackend")
    # login() rotates the session key, which login() itself already wrote
    # impersonator_id into above — re-set defensively in case a future
    # Django login() implementation ever clears extra session keys first.
    request.session[IMPERSONATOR_SESSION_KEY] = str(impersonator.pk)


def end_impersonation(request: HttpRequest, *, impersonator: Any) -> None:
    """Restores the staff session. The audit row (``impersonation.end``)
    is written by the caller, same as ``start_impersonation``."""
    del request.session[IMPERSONATOR_SESSION_KEY]
    login(request, impersonator, backend="django.contrib.auth.backends.ModelBackend")

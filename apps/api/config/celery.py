import os
from fnmatch import fnmatch
from typing import Any

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("keel")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


# Four queues, routed by cost profile, not by domain (PRD §5,
# docs/plans/phase-5.md 5.1). The split exists so a hundred queued
# third-party calls (Stripe syncs, OAuth refreshes) cannot delay a
# password-reset email, and so a slow scheduled rollup cannot starve
# either. Projects add queues for new cost profiles as they appear;
# never collapse these four back together — the moment "email" and
# "external" share a queue, one third-party outage becomes a login
# outage too.
#
# Routed by task *name pattern*, not by an explicit per-task queue
# argument on ``@task``/``@shared_task`` — that keeps the routing table
# in one place (here) instead of scattered across every task module,
# where it would silently drift as tasks move between modules.
QUEUE_DEFAULT = "default"
QUEUE_EMAIL = "email"
QUEUE_EXTERNAL = "external"
QUEUE_SCHEDULED = "scheduled"

# Ordered: first pattern to match wins. Scheduled (beat-triggered) jobs
# are matched by module path ahead of the narrower email/external
# patterns below, since e.g. the trial-ending job both queries the DB
# and sends email but is fundamentally a scheduled rollup, not a
# transactional send.
_QUEUE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("keel.jobs.tasks.*", QUEUE_SCHEDULED),
    ("keel.notifications.tasks.*", QUEUE_EMAIL),
    ("keel.billing.tasks.dispatch_stripe_event", QUEUE_EXTERNAL),
    ("keel.billing.tasks.sync_seat_quantity_task", QUEUE_EXTERNAL),
    ("keel.connections.tasks.*", QUEUE_EXTERNAL),
)


def route_task(
    name: str, args: Any, kwargs: Any, options: Any, task: Any = None, **kw: Any
) -> dict[str, str]:
    for pattern, queue in _QUEUE_PATTERNS:
        if fnmatch(name, pattern):
            return {"queue": queue}
    return {"queue": QUEUE_DEFAULT}


app.conf.task_routes = (route_task,)

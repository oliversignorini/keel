"""One-line delegations to services (PRD §4 per-app structure;
docs/plans/phase-6.md 6.D). Tier-1 shim (``keel.core.tasks``) — see that
module's docstring for the fire-and-forget/multi-step boundary.
"""

from keel.core.tasks import task
from keel.widgets import services
from keel.widgets.models import Widget


@task
def notify_widget_created_task(widget_id: str) -> None:
    widget = Widget.objects.get(pk=widget_id)
    services._notify_widget_created(widget.id)

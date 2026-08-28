"""One-line delegations to services (CLAUDE.md's per-app file shape).
Tier-1 shim (``keel.core.tasks``) — see that module's docstring for the
fire-and-forget / multi-step boundary. A task that grows a second step
belongs in ``keel/jobs/``, not here.
"""

from keel.core.tasks import task
from keel.widgets import services
from keel.widgets.models import Widget


@task
def notify_widget_created_task(widget_id: str) -> None:
    widget = Widget.objects.get(pk=widget_id)
    services._notify_widget_created(widget.id)

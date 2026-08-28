"""One-line delegations to services (CLAUDE.md's per-app file shape).
Tier-1 shim (``keel.core.tasks``) — see that module's docstring for the
fire-and-forget / multi-step boundary. A task that grows a second step
belongs in ``keel/jobs/``, not here.
"""

from keel.__app__ import services
from keel.__app__.models import __Resource__
from keel.core.tasks import task


@task
def notify___resource___created_task(__resource___id: str) -> None:
    __resource__ = __Resource__.objects.get(pk=__resource___id)
    services._notify___resource___created(__resource__.id)

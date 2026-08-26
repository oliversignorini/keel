"""``POST /api/v1/impersonation/exit/`` (PRD §6 "Impersonation";
docs/plans/phase-8.md 8.3). The frontend `<ImpersonationBanner>`'s only
action — everything else about starting/ending impersonation happens in
Django admin (``keel.accounts.admin``'s "Impersonate" action), which the
banner has no reason to duplicate."""

from django.http import Http404
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from keel.audit.models import AuditLog
from keel.core.impersonation import end_impersonation, get_impersonator_id


class ImpersonationExitView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request: Request) -> Response:
        from keel.accounts.models import User

        impersonator_id = get_impersonator_id(request)
        if impersonator_id is None:
            raise Http404
        impersonator = User.objects.get(pk=impersonator_id)
        target = request.user
        end_impersonation(request, impersonator=impersonator)
        AuditLog.objects.create(
            actor=target,
            impersonator=impersonator,
            action="impersonation.end",
            target_type="User",
            target_id=str(target.pk),
        )
        return Response(status=204)

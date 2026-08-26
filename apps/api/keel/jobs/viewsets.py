"""``organizations/<org_slug>/jobs/`` (PRD §7 jobs endpoints).

``idempotency_scoped = True`` opts POST into
``keel.jobs.idempotency.IdempotencyKeyMiddleware``. The stream endpoint
(``GET .../jobs/stream/``) deliberately lives elsewhere — it is served
by the dedicated ASGI service, not this (sync) viewset; see
``keel/jobs/sse.py`` and ``config/urls_stream.py``.
"""

from typing import Any, ClassVar

from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from keel.core.authz import OrgScopedViewSet
from keel.jobs import selectors, services
from keel.jobs.serializers import JobCreateSerializer, JobSerializer
from keel.organizations.permissions import Perm


class JobViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    OrgScopedViewSet,
):
    serializer_class = JobSerializer
    organization_scoped = True
    idempotency_scoped = True
    test_factory = "keel.jobs.tests.factories.job_factory"

    required_permissions: tuple[str, ...] = (Perm.JOBS_VIEW,)

    _ACTION_PERMISSIONS: ClassVar[dict[str, tuple[str, ...]]] = {
        "list": (Perm.JOBS_VIEW,),
        "retrieve": (Perm.JOBS_VIEW,),
        "create": (Perm.JOBS_CREATE,),
        "cancel": (Perm.JOBS_CREATE,),
    }

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        self.required_permissions = self._ACTION_PERMISSIONS.get(
            self.action, self.required_permissions
        )
        super().initial(request, *args, **kwargs)

    def get_queryset(self) -> Any:
        queryset = selectors.list_jobs_for_organization(self.organization)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = JobCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = services.create_job(
            organization=self.organization,
            actor=request.user,
            type=serializer.validated_data["type"],
            params=serializer.validated_data.get("params") or {},
            idempotency_key=request.headers.get("Idempotency-Key", ""),
        )
        return Response(JobSerializer(job).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        job = services.cancel_job(job=self.get_object(), actor=request.user)
        return Response(JobSerializer(job).data)

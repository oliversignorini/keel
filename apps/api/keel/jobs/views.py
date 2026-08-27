"""``orgs/<org_slug>/jobs/`` (PRD §7 jobs endpoints; phase-10.md
10.C). The stream endpoint (``GET .../jobs/stream/``) lives elsewhere —
it is served by the dedicated ASGI service, not this router; see
``keel/jobs/sse.py`` and ``config/urls_stream.py``. Neither ever used
DRF, so neither needed migrating.

``create_job`` calls ``keel.jobs.idempotency.check_and_claim`` explicitly
at the top of its body — the Ninja counterpart to DRF's
``idempotency_scoped = True`` class attribute, which
``IdempotencyKeyMiddleware.process_view`` detected via ``view_func.cls``,
a hook Ninja's routing has no equivalent of. See that module's docstring.
"""

from typing import Any

from django.http import Http404
from ninja import Status

from keel.core.ninja_authz import OrgScopedResource, keel_router, resolve_and_authorize
from keel.core.ninja_pagination import Page, paginate
from keel.jobs import idempotency, selectors, services
from keel.jobs.schemas import JobCreateIn, JobOut
from keel.organizations.permissions import Perm


class JobResource(OrgScopedResource):
    router = keel_router(tags=["jobs"])
    organization_scoped = True
    test_factory = "keel.jobs.tests.factories.job_factory"
    required_permissions = (Perm.JOBS_VIEW,)
    detail_url_template = "/api/v1/orgs/{org_slug}/jobs/{pk}/"


router = JobResource.router


@router.get("/{org_slug}/jobs/", response=Page[JobOut])
def list_jobs(request: Any, org_slug: str) -> dict:
    organization = resolve_and_authorize(request, org_slug, (Perm.JOBS_VIEW,))
    queryset = selectors.list_jobs_for_organization(organization)
    status_filter = request.GET.get("status")
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    return paginate(request, queryset)


@router.post("/{org_slug}/jobs/", response={202: JobOut})
def create_job(request: Any, org_slug: str, payload: JobCreateIn) -> Any:
    organization = resolve_and_authorize(request, org_slug, (Perm.JOBS_CREATE,))

    cached_response = idempotency.check_and_claim(request, org_slug)
    if cached_response is not None:
        return cached_response

    job = services.create_job(
        organization=organization,
        actor=request.auth,
        type=payload.type,
        params=payload.params or {},
        idempotency_key=request.headers.get("Idempotency-Key", ""),
    )
    return Status(202, job)


@router.get("/{org_slug}/jobs/{pk}/", response=JobOut)
def retrieve_job(request: Any, org_slug: str, pk: str) -> Any:
    organization = resolve_and_authorize(request, org_slug, (Perm.JOBS_VIEW,))
    job = selectors.list_jobs_for_organization(organization).filter(pk=pk).first()
    if job is None:
        raise Http404
    return job


@router.post("/{org_slug}/jobs/{pk}/cancel/", response=JobOut)
def cancel_job(request: Any, org_slug: str, pk: str) -> Any:
    organization = resolve_and_authorize(request, org_slug, (Perm.JOBS_CREATE,))
    job = selectors.list_jobs_for_organization(organization).filter(pk=pk).first()
    if job is None:
        raise Http404
    return services.cancel_job(job=job, actor=request.auth)

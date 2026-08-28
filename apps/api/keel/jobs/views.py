"""``orgs/<org_slug>/jobs/`` (PRD §7 jobs endpoints). The stream endpoint
(``GET .../jobs/stream/``) lives elsewhere — it is served by the
dedicated ASGI service, not this router; see ``keel/jobs/sse.py`` and
``config/urls_stream.py``.

``create_job`` is decorated ``@idempotent``. See ``keel.core.idempotency``'s
docstring for how the idempotency key is read and matched.
"""

from typing import Any

from ninja import Status

from keel.core.ninja_authz import OrgScopedResource, keel_router, resolve_and_authorize
from keel.core.idempotency import idempotent
from keel.core.ninja_pagination import paginated
from keel.core.selectors import get_scoped_or_404
from keel.jobs import selectors, services
from keel.jobs.schemas import JobCreateIn, JobOut, JobStatus
from keel.organizations.permissions import Perm


class JobResource(OrgScopedResource):
    router = keel_router(tags=["jobs"])
    organization_scoped = True
    test_factory = "keel.jobs.tests.factories.job_factory"
    required_permissions = (Perm.JOBS_VIEW,)
    detail_url_template = "/api/v1/orgs/{org_slug}/jobs/{id}/"


router = JobResource.router


@paginated(router.get, "/{org_slug}/jobs/", JobOut, operation_id="listJobs")
def list_jobs(
    request: Any,
    org_slug: str,
    status: JobStatus | None = None,
    cursor: str | None = None,
    limit: int | None = None,
) -> Any:
    organization = resolve_and_authorize(request, org_slug, (Perm.JOBS_VIEW,))
    return selectors.list_jobs_for_organization(organization, status=status)


@router.post("/{org_slug}/jobs/", response={202: JobOut, 200: JobOut}, operation_id="createJob")
@idempotent
def create_job(request: Any, org_slug: str, payload: JobCreateIn) -> Any:
    organization = resolve_and_authorize(request, org_slug, (Perm.JOBS_CREATE,))
    job = services.create_job(
        organization=organization,
        actor=request.auth,
        type=payload.type,
        params=payload.params or {},
        idempotency_key=request.headers.get("Idempotency-Key", ""),
    )
    return Status(202, job)


@router.get("/{org_slug}/jobs/{id}/", response=JobOut, operation_id="retrieveJob")
def retrieve_job(request: Any, org_slug: str, id: str) -> Any:
    organization = resolve_and_authorize(request, org_slug, (Perm.JOBS_VIEW,))
    return get_scoped_or_404(selectors.list_jobs_for_organization(organization), id)


@router.post("/{org_slug}/jobs/{id}/cancel/", response=JobOut, operation_id="cancelJob")
def cancel_job(request: Any, org_slug: str, id: str) -> Any:
    organization = resolve_and_authorize(request, org_slug, (Perm.JOBS_CREATE,))
    job = get_scoped_or_404(selectors.list_jobs_for_organization(organization), id)
    return services.cancel_job(job=job, actor=request.auth)

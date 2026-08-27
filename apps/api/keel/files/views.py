"""Presigned upload endpoints (PRD §5; docs/plans/phase-5.md 5.6;
phase-10.md 10.C). Each resolves ``org_slug`` via ``resolve_and_authorize``
and every query below is filtered by that organisation, which is what
makes a cross-tenant lookup 404 instead of ever exposing another
organisation's row (docs/plans/phase-5.md 5.6, "unreadable across
tenants").

``FileUploadResource`` declares only what PRD §4 invariant 7's
tenant-isolation walk needs (``required_permissions`` matching
``retrieve_upload``'s own check, ``test_factory``, ``detail_url_template``)
— routes still call ``resolve_and_authorize`` directly per action, same as
``keel.billing.views``' plain routes, rather than adopting a
per-action-dispatch base class.
"""

from typing import Any

from django.http import Http404
from ninja import Status

from keel.core.ninja_authz import OrgScopedResource, keel_router, resolve_and_authorize
from keel.files import services
from keel.files.models import FileUpload
from keel.files.schemas import FileUploadOut, PresignedUploadRequest
from keel.organizations.permissions import Perm


class FileUploadResource(OrgScopedResource):
    router = keel_router(tags=["files"])
    organization_scoped = True
    test_factory = "keel.files.tests.factories.file_upload_factory"
    required_permissions = (Perm.FILES_VIEW,)
    detail_url_template = "/api/v1/orgs/{org_slug}/files/{id}/"


router = FileUploadResource.router


@router.post("/{org_slug}/files/", response={201: dict}, operation_id="createUpload")
def create_upload(request: Any, org_slug: str, payload: PresignedUploadRequest) -> Any:
    organization = resolve_and_authorize(request, org_slug, (Perm.FILES_MANAGE,))
    file_upload, upload_url = services.create_presigned_upload(
        organization=organization,
        actor=request.auth,
        filename=payload.filename,
        content_type=payload.content_type,
        size=payload.size,
    )
    return Status(
        201, {"file": FileUploadOut.from_orm(file_upload).dict(), "upload_url": upload_url}
    )


@router.post(
    "/{org_slug}/files/{id}/complete/", response=FileUploadOut, operation_id="completeUpload"
)
def complete_upload(request: Any, org_slug: str, id: str) -> FileUpload:
    organization = resolve_and_authorize(request, org_slug, (Perm.FILES_MANAGE,))
    file_upload = FileUpload.objects.filter(pk=id, organization=organization).first()
    if file_upload is None:
        raise Http404
    services.complete_upload(file_upload=file_upload)
    return file_upload


@router.get("/{org_slug}/files/{id}/", response=FileUploadOut, operation_id="retrieveUpload")
def retrieve_upload(request: Any, org_slug: str, id: str) -> FileUpload:
    """Scoped to ``organization`` in the same lookup as the completion
    view above — the mechanism the cross-tenant test in
    ``keel/files/tests/test_uploads.py`` exercises directly."""
    organization = resolve_and_authorize(request, org_slug, (Perm.FILES_VIEW,))
    file_upload = FileUpload.objects.filter(pk=id, organization=organization).first()
    if file_upload is None:
        raise Http404
    return file_upload

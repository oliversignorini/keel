"""Presigned upload endpoints (PRD §5; docs/plans/phase-5.md 5.6;
phase-10.md 10.C). Each resolves ``org_slug`` via ``resolve_and_authorize``
and every query below is filtered by that organisation, which is what
makes a cross-tenant lookup 404 instead of ever exposing another
organisation's row (docs/plans/phase-5.md 5.6, "unreadable across
tenants") — no separate ``OrgScopedResource`` needed, same reasoning
``keel.billing.views`` documents for its own plain routes.
"""

from typing import Any

from django.http import Http404
from ninja import Status

from keel.core.ninja_authz import keel_router, resolve_and_authorize
from keel.files import services
from keel.files.models import FileUpload
from keel.files.schemas import FileUploadOut, PresignedUploadRequest
from keel.organizations.permissions import Perm

router = keel_router(tags=["files"])


@router.post("/{org_slug}/files/", response={201: dict})
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


@router.post("/{org_slug}/files/{file_id}/complete/", response=FileUploadOut)
def complete_upload(request: Any, org_slug: str, file_id: str) -> FileUpload:
    organization = resolve_and_authorize(request, org_slug, (Perm.FILES_MANAGE,))
    file_upload = FileUpload.objects.filter(pk=file_id, organization=organization).first()
    if file_upload is None:
        raise Http404
    services.complete_upload(file_upload=file_upload)
    return file_upload


@router.get("/{org_slug}/files/{file_id}/", response=FileUploadOut)
def retrieve_upload(request: Any, org_slug: str, file_id: str) -> FileUpload:
    """Scoped to ``organization`` in the same lookup as the completion
    view above — the mechanism the cross-tenant test in
    ``keel/files/tests/test_uploads.py`` exercises directly."""
    organization = resolve_and_authorize(request, org_slug, (Perm.FILES_VIEW,))
    file_upload = FileUpload.objects.filter(pk=file_id, organization=organization).first()
    if file_upload is None:
        raise Http404
    return file_upload

"""File-upload endpoints (PRD §5). Each resolves ``org_slug`` via
``resolve_and_authorize`` and every query below is filtered by that
organisation, which is what makes a cross-tenant lookup 404 instead of
ever exposing another organisation's row.

``FileUploadResource`` declares what PRD §4 invariant 7's
tenant-isolation walk needs (``required_permissions`` matching
``retrieve_upload``'s own check, ``test_factory``, ``detail_url_template``)
— routes still call ``resolve_and_authorize`` directly per action, same
as ``keel.billing.views``' plain routes, rather than adopting a
per-action-dispatch base class."""

from typing import Any

from django.http import FileResponse, Http404
from ninja import Status

from keel.core.authz import OrgScopedResource, keel_router, resolve_and_authorize
from keel.core.idempotency import idempotent
from keel.core.pagination import Page, paginate
from keel.files import selectors, services, storage
from keel.files.models import FileUpload
from keel.files.schemas import (
    FileDownloadUrlOut,
    FileUploadOut,
    PresignedUploadOut,
    PresignedUploadRequest,
)
from keel.organizations.permissions import Perm


class FileUploadResource(OrgScopedResource):
    router = keel_router(tags=["files"])
    organization_scoped = True
    test_factory = "keel.files.tests.factories.file_upload_factory"
    required_permissions = (Perm.FILES_VIEW,)
    detail_url_template = "/api/v1/orgs/{org_slug}/files/{id}/"


router = FileUploadResource.router


@router.get("/{org_slug}/files/", response=Page[FileUploadOut], operation_id="listFiles")
def list_files(
    request: Any, org_slug: str, cursor: str | None = None, limit: int | None = None
) -> dict:
    organization = resolve_and_authorize(request, org_slug, (Perm.FILES_VIEW,))
    return paginate(request, selectors.list_files(organization))


@router.post(
    "/{org_slug}/files/",
    response={201: PresignedUploadOut, 200: PresignedUploadOut},
    operation_id="createUpload",
)
@idempotent
def create_upload(request: Any, org_slug: str, payload: PresignedUploadRequest) -> Any:
    organization = resolve_and_authorize(request, org_slug, (Perm.FILES_MANAGE,))
    file_upload, upload_url = services.create_presigned_upload(
        organization=organization,
        actor=request.auth,
        filename=payload.filename,
        content_type=payload.content_type,
        size=payload.size,
        checksum_sha256=payload.checksum_sha256,
    )
    return Status(201, {"file": file_upload, "upload_url": upload_url})


@router.post(
    "/{org_slug}/files/{id}/complete/", response=FileUploadOut, operation_id="completeUpload"
)
def complete_upload(request: Any, org_slug: str, id: str) -> FileUpload:
    organization = resolve_and_authorize(request, org_slug, (Perm.FILES_MANAGE,))
    file_upload = selectors.get_upload_or_404(organization, id)
    return services.complete_upload(file_upload=file_upload)


@router.get("/{org_slug}/files/{id}/", response=FileUploadOut, operation_id="retrieveUpload")
def retrieve_upload(request: Any, org_slug: str, id: str) -> FileUpload:
    """Scoped to ``organization`` in the same lookup as every other
    action above — the mechanism the cross-tenant test in
    ``keel/files/tests/test_uploads.py`` exercises directly."""
    organization = resolve_and_authorize(request, org_slug, (Perm.FILES_VIEW,))
    return selectors.get_upload_or_404(organization, id)


@router.get(
    "/{org_slug}/files/{id}/download/",
    response=FileDownloadUrlOut,
    operation_id="getFileDownloadUrl",
)
def get_download_url(request: Any, org_slug: str, id: str) -> Any:
    """Returns a fresh, short-lived download URL rather than embedding
    one in every list/retrieve response — a presigned GET URL is a
    credential in its own right (PRD §4 invariant 7's "unreadable across
    tenants" applies to it too), so it's only minted for the caller who
    just proved, via ``resolve_and_authorize``, that they're allowed to
    read this row."""
    organization = resolve_and_authorize(request, org_slug, (Perm.FILES_VIEW,))
    file_upload = selectors.get_upload_or_404(organization, id)
    if file_upload.status != FileUpload.STATUS_AVAILABLE:
        raise Http404
    adapter = storage.get_storage()
    download_url = adapter.generate_presigned_download(
        key=file_upload.key, organization_slug=org_slug, file_upload_id=str(file_upload.id)
    )
    return {"download_url": download_url}


@router.delete("/{org_slug}/files/{id}/", response={204: None}, operation_id="deleteFile")
def delete_file(request: Any, org_slug: str, id: str) -> Status[None]:
    organization = resolve_and_authorize(request, org_slug, (Perm.FILES_MANAGE,))
    file_upload = selectors.get_upload_or_404(organization, id)
    services.delete_file(file_upload=file_upload, actor=request.auth)
    return Status(204, None)


# --- Local-filesystem dev backend only (keel.files.storage.LocalFileSystemStorage) ---
# S3-compatible backends never reach these routes — their presigned URLs
# point straight at the bucket. These exist purely so a developer running
# without the MinIO container still gets a working upload/download
# round-trip end to end (docs/storage.md).


@router.put(
    "/{org_slug}/files/{id}/local-object/", response={204: None}, operation_id="localObjectUpload"
)
def local_object_upload(request: Any, org_slug: str, id: str) -> Status[None]:
    organization = resolve_and_authorize(request, org_slug, (Perm.FILES_MANAGE,))
    file_upload = selectors.get_upload_or_404(organization, id)
    adapter = storage.get_storage()
    if not isinstance(adapter, storage.LocalFileSystemStorage):
        raise Http404
    if file_upload.status != FileUpload.STATUS_PENDING:
        raise Http404
    content_type = request.META.get("CONTENT_TYPE") or file_upload.content_type
    adapter.write(key=file_upload.key, content_type=content_type, stream=request)
    return Status(204, None)


@router.get("/{org_slug}/files/{id}/local-object/", operation_id="localObjectDownload")
def local_object_download(request: Any, org_slug: str, id: str) -> Any:
    organization = resolve_and_authorize(request, org_slug, (Perm.FILES_VIEW,))
    file_upload = selectors.get_upload_or_404(organization, id)
    adapter = storage.get_storage()
    if not isinstance(adapter, storage.LocalFileSystemStorage):
        raise Http404
    fh = adapter.open_for_read(key=file_upload.key)
    if fh is None:
        raise Http404
    return FileResponse(fh, content_type=file_upload.content_type)

"""Presigned upload endpoints (PRD §5; docs/plans/phase-5.md 5.6). Plain
``APIView``s in ``keel.billing.views``' ``_OrganizationBillingView``
shape — each resolves ``org_slug`` and every query below is filtered by
that organisation, which is what makes a cross-tenant lookup 404 instead
of ever exposing another organisation's row (docs/plans/phase-5.md 5.6,
"unreadable across tenants")."""

from django.http import Http404
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from keel.core.authz import has_perm
from keel.core.exceptions import PermissionDeniedWithReason
from keel.files import services
from keel.files.models import FileUpload
from keel.files.serializers import FileUploadSerializer, PresignedUploadRequestSerializer
from keel.organizations.models import Organization
from keel.organizations.permissions import Perm
from keel.organizations.resolvers import resolve_organization


class _OrganizationFilesView(APIView):
    permission_classes = (IsAuthenticated,)
    required_permission: str

    def _get_organization(self, request: Request, org_slug: str) -> Organization:
        organization = resolve_organization(request, org_slug)
        if organization is None:
            raise Http404
        decision = has_perm(request.user, organization, self.required_permission)
        if not decision.allowed:
            raise PermissionDeniedWithReason(
                code=decision.reason or "permission_denied", details=decision.details
            )
        return organization


class FileUploadCreateView(_OrganizationFilesView):
    """``POST /organizations/<org_slug>/files/``."""

    required_permission = Perm.FILES_MANAGE

    def post(self, request: Request, org_slug: str) -> Response:
        organization = self._get_organization(request, org_slug)
        serializer = PresignedUploadRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        file_upload, upload_url = services.create_presigned_upload(
            organization=organization,
            actor=request.user,
            **serializer.validated_data,
        )
        return Response(
            {"file": FileUploadSerializer(file_upload).data, "upload_url": upload_url},
            status=201,
        )


class FileUploadCompleteView(_OrganizationFilesView):
    """``POST /organizations/<org_slug>/files/<file_id>/complete/``."""

    required_permission = Perm.FILES_MANAGE

    def post(self, request: Request, org_slug: str, file_id: str) -> Response:
        organization = self._get_organization(request, org_slug)
        file_upload = FileUpload.objects.filter(pk=file_id, organization=organization).first()
        if file_upload is None:
            raise Http404
        services.complete_upload(file_upload=file_upload)
        return Response(FileUploadSerializer(file_upload).data)


class FileUploadDetailView(_OrganizationFilesView):
    """``GET /organizations/<org_slug>/files/<file_id>/``. Scoped to
    ``organization`` in the same lookup as the completion view above —
    the mechanism the cross-tenant test in
    ``keel/files/tests/test_uploads.py`` exercises directly."""

    required_permission = Perm.FILES_VIEW

    def get(self, request: Request, org_slug: str, file_id: str) -> Response:
        organization = self._get_organization(request, org_slug)
        file_upload = FileUpload.objects.filter(pk=file_id, organization=organization).first()
        if file_upload is None:
            raise Http404
        return Response(FileUploadSerializer(file_upload).data)

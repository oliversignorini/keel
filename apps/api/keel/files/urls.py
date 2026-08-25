"""URL wiring for files (PRD §5; docs/plans/phase-5.md 5.6)."""

from django.urls import path

from keel.files import views

urlpatterns = [
    path(
        "organizations/<slug:org_slug>/files/",
        views.FileUploadCreateView.as_view(),
        name="file-upload-create",
    ),
    path(
        "organizations/<slug:org_slug>/files/<uuid:file_id>/",
        views.FileUploadDetailView.as_view(),
        name="file-upload-detail",
    ),
    path(
        "organizations/<slug:org_slug>/files/<uuid:file_id>/complete/",
        views.FileUploadCompleteView.as_view(),
        name="file-upload-complete",
    ),
]

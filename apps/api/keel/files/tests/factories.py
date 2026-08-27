"""Row factory used both by ``FileUploadResource.test_factory`` (PRD §4
invariant 7 — the cross-org meta-test walk) and directly by this app's
own tests."""

from django.utils.crypto import get_random_string

from keel.accounts.models import User
from keel.files.models import FileUpload
from keel.organizations.models import Organization


def file_upload_factory(organization: Organization) -> FileUpload:
    uploader = User.objects.create_user(
        email=f"file-uploader-{organization.pk}-{get_random_string(6).lower()}@example.com",
        password="s3cret-pass",
    )
    return FileUpload.objects.create(
        organization=organization,
        uploader=uploader,
        key=f"{organization.pk}/{get_random_string(12)}",
        content_type="application/pdf",
        size=1,
        status=FileUpload.STATUS_PENDING,
    )

"""Proves the acceptance criterion "switching storage backend is a
settings change only": the exact same upload -> complete -> download
round trip as ``test_uploads.py``'s moto-backed suite, run against
``LocalFileSystemStorage`` instead, with nothing touched but
``STORAGES["files"]["BACKEND"]``."""

import hashlib
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from django.test import Client as APIClient

from keel.accounts.models import User
from keel.files.models import FileUpload
from keel.organizations import services
from keel.organizations.models import Organization

pytestmark = pytest.mark.django_db

_BYTES = b"local disk upload contents"
_SHA256 = hashlib.sha256(_BYTES).hexdigest()


@pytest.fixture
def local_storage_settings(settings: Any) -> Iterator[None]:
    tmp_root = Path(tempfile.mkdtemp(prefix="keel-files-test-"))
    # A full re-assignment, not an in-place mutation of the existing
    # dict: pytest-django's ``settings`` fixture only restores an
    # attribute it saw *reassigned* (``settings.STORAGES = ...``) — it
    # can't detect (or undo) a mutation of the dict already sitting
    # there, which would otherwise leak this override into every test
    # that runs afterwards in the same process.
    settings.STORAGES = {
        **settings.STORAGES,
        "files": {
            "BACKEND": "keel.files.storage.LocalFileSystemStorage",
            "OPTIONS": {"root": str(tmp_root)},
        },
    }
    yield
    shutil.rmtree(tmp_root, ignore_errors=True)


def _org_with_owner() -> tuple[Organization, User]:
    owner = User.objects.create_user(email="local-owner@example.com", password="s3cret-pass")
    org = services.create_organization(name="Acme", slug="acme-local", created_by=owner)
    return org, owner


def test_full_flow_against_the_local_filesystem_backend(local_storage_settings: None) -> None:
    org, owner = _org_with_owner()
    client = APIClient()
    client.force_login(owner)

    create_response = client.post(
        f"/api/v1/orgs/{org.slug}/files/",
        {
            "filename": "notes.txt",
            "content_type": "text/plain",
            "size": len(_BYTES),
            "checksum_sha256": _SHA256,
        },
        content_type="application/json",
    )
    assert create_response.status_code == 201
    body = create_response.json()
    file_id = body["file"]["id"]
    upload_url = body["upload_url"]
    assert upload_url == f"/api/v1/orgs/{org.slug}/files/{file_id}/local-object/"

    put_response = client.put(upload_url, data=_BYTES, content_type="text/plain")
    assert put_response.status_code == 204

    complete_response = client.post(f"/api/v1/orgs/{org.slug}/files/{file_id}/complete/")
    assert complete_response.status_code == 200
    assert complete_response.json()["status"] == FileUpload.STATUS_AVAILABLE
    assert complete_response.json()["size"] == len(_BYTES)

    download_url_response = client.get(f"/api/v1/orgs/{org.slug}/files/{file_id}/download/")
    assert download_url_response.status_code == 200
    download_url = download_url_response.json()["download_url"]
    assert download_url == f"/api/v1/orgs/{org.slug}/files/{file_id}/local-object/"

    download_response = client.get(download_url)
    assert download_response.status_code == 200
    assert b"".join(download_response.streaming_content) == _BYTES  # type: ignore[attr-defined]

    delete_response = client.delete(f"/api/v1/orgs/{org.slug}/files/{file_id}/")
    assert delete_response.status_code == 204

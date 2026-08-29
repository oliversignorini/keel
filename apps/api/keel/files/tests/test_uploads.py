"""Presigned direct upload. Uses ``moto``'s mocked S3 rather than a real
MinIO/R2 — see ``keel.files.storage.S3CompatibleStorage`` and
``infra/compose.dev.yml``'s ``minio`` service for the two real-environment
stand-ins this project uses instead of real R2 credentials, which don't
exist."""

import hashlib
import io
from typing import Any

import boto3
import pytest
import requests
from django.conf import settings
from django.test import Client as APIClient
from moto import mock_aws

from keel.accounts.models import User
from keel.files.models import FileUpload
from keel.organizations import services
from keel.organizations.models import Membership, Organization
from keel.organizations.roles import PRESET_MEMBER, seed_preset_roles

pytestmark = pytest.mark.django_db

_counter = 0

_PDF_BYTES = b"%PDF-1.4 fake pdf contents for the test suite"
_PDF_SHA256 = hashlib.sha256(_PDF_BYTES).hexdigest()


def _user(prefix: str = "user") -> User:
    global _counter
    _counter += 1
    return User.objects.create_user(
        email=f"{prefix}-{_counter}@example.com", password="s3cret-pass"
    )


def _org_with_owner() -> tuple[Organization, User]:
    global _counter
    _counter += 1
    owner = _user("owner")
    org = services.create_organization(name="Acme", slug=f"acme-{_counter}", actor=owner)
    return org, owner


def _add_member(org: Organization) -> User:
    member = _user("member")
    role = seed_preset_roles()[PRESET_MEMBER]
    Membership.objects.create(
        organization=org, user=member, role=role, status=Membership.STATUS_ACTIVE
    )
    return member


def _client_for(user: User) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


@pytest.fixture(autouse=True)
def _mocked_bucket():
    with mock_aws():
        boto3.client(
            "s3",
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            region_name="us-east-1",
        ).create_bucket(Bucket=settings.R2_BUCKET)
        yield


def _create_upload(client: APIClient, org: Organization, **overrides: object) -> Any:
    payload = {
        "filename": "report.pdf",
        "content_type": "application/pdf",
        "size": len(_PDF_BYTES),
        "checksum_sha256": _PDF_SHA256,
        **overrides,
    }
    response = client.post(
        f"/api/v1/orgs/{org.slug}/files/", payload, content_type="application/json"
    )
    assert response.status_code == 201, response.content
    return response.json()


def test_full_flow_presign_then_direct_upload_then_complete() -> None:
    org, owner = _org_with_owner()
    client = _client_for(owner)

    body = _create_upload(client, org)
    assert body["file"]["status"] == FileUpload.STATUS_PENDING
    assert body["file"]["filename"] == "report.pdf"
    file_id = body["file"]["id"]
    upload_url = body["upload_url"]
    assert str(org.pk) in FileUpload.objects.get(pk=file_id).key

    # "the browser uploads straight to storage" — done here with a plain
    # PUT against the presigned URL, exactly what a browser's fetch()
    # would do.
    put_response = requests.put(
        upload_url, data=io.BytesIO(_PDF_BYTES), headers={"Content-Type": "application/pdf"}
    )
    assert put_response.status_code == 200

    complete_response = client.post(f"/api/v1/orgs/{org.slug}/files/{file_id}/complete/")
    assert complete_response.status_code == 200
    completed = complete_response.json()
    assert completed["status"] == FileUpload.STATUS_AVAILABLE
    assert completed["size"] == len(_PDF_BYTES)

    file_upload = FileUpload.objects.get(pk=file_id)
    assert file_upload.status == FileUpload.STATUS_AVAILABLE
    assert file_upload.completed_at is not None
    assert file_upload.etag

    # list
    list_response = client.get(f"/api/v1/orgs/{org.slug}/files/")
    assert list_response.status_code == 200
    assert [row["id"] for row in list_response.json()["results"]] == [file_id]

    # retrieve
    retrieve_response = client.get(f"/api/v1/orgs/{org.slug}/files/{file_id}/")
    assert retrieve_response.status_code == 200
    assert retrieve_response.json()["status"] == FileUpload.STATUS_AVAILABLE

    # download URL
    download_response = client.get(f"/api/v1/orgs/{org.slug}/files/{file_id}/download/")
    assert download_response.status_code == 200
    assert download_response.json()["download_url"]

    # delete (tombstone)
    delete_response = client.delete(f"/api/v1/orgs/{org.slug}/files/{file_id}/")
    assert delete_response.status_code == 204
    file_upload.refresh_from_db()
    assert file_upload.status == FileUpload.STATUS_DELETED
    assert file_upload.deleted_at is not None

    # a deleted file drops out of the list ...
    list_after_delete = client.get(f"/api/v1/orgs/{org.slug}/files/")
    assert list_after_delete.json()["results"] == []
    # ... but its detail route still answers (soft delete, not a 404)
    retrieve_after_delete = client.get(f"/api/v1/orgs/{org.slug}/files/{file_id}/")
    assert retrieve_after_delete.status_code == 200
    assert retrieve_after_delete.json()["status"] == FileUpload.STATUS_DELETED


def test_complete_before_the_object_actually_exists_is_rejected() -> None:
    org, owner = _org_with_owner()
    client = _client_for(owner)

    body = _create_upload(client, org)
    file_id = body["file"]["id"]

    complete_response = client.post(f"/api/v1/orgs/{org.slug}/files/{file_id}/complete/")

    assert complete_response.status_code == 422
    assert FileUpload.objects.get(pk=file_id).status == FileUpload.STATUS_PENDING


def test_a_corrupted_upload_is_rejected_on_complete() -> None:
    """The bytes that actually land in storage don't match the checksum
    the client declared at create time — services.complete_upload must
    catch this itself ("a corrupted upload is rejected"), since neither
    MinIO nor moto can be relied on to reject
    a mismatched checksum at PUT time (keel.files.storage.ObjectStorage's
    ``compute_sha256`` docstring)."""
    org, owner = _org_with_owner()
    client = _client_for(owner)

    body = _create_upload(client, org)
    file_id = body["file"]["id"]
    upload_url = body["upload_url"]

    requests.put(
        upload_url,
        data=io.BytesIO(b"not the bytes the client declared"),
        headers={"Content-Type": "application/pdf"},
    )

    complete_response = client.post(f"/api/v1/orgs/{org.slug}/files/{file_id}/complete/")

    assert complete_response.status_code == 200
    body = complete_response.json()
    assert body["status"] == FileUpload.STATUS_FAILED
    assert body["failure_reason"] == "checksum_mismatch"
    file_upload = FileUpload.objects.get(pk=file_id)
    assert file_upload.status == FileUpload.STATUS_FAILED


def test_create_upload_rejects_a_size_over_the_configured_limit(settings: Any) -> None:
    org, owner = _org_with_owner()
    client = _client_for(owner)

    response = client.post(
        f"/api/v1/orgs/{org.slug}/files/",
        {
            "filename": "huge.bin",
            "content_type": "application/octet-stream",
            "size": settings.FILES_MAX_UPLOAD_SIZE_BYTES + 1,
            "checksum_sha256": _PDF_SHA256,
        },
        content_type="application/json",
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "upload_too_large"


def test_create_upload_rejects_a_disallowed_content_type(settings: Any) -> None:
    org, owner = _org_with_owner()
    client = _client_for(owner)
    settings.FILES_ALLOWED_CONTENT_TYPES = ["application/pdf"]

    response = client.post(
        f"/api/v1/orgs/{org.slug}/files/",
        {
            "filename": "script.exe",
            "content_type": "application/x-msdownload",
            "size": 10,
            "checksum_sha256": _PDF_SHA256,
        },
        content_type="application/json",
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "content_type_not_allowed"


def test_completing_reports_the_server_observed_size_not_the_clients_claim() -> None:
    """size/content_type/etag come from ``HeadObject``, not the client —
    the client under-declares the size at create time; what actually
    lands in storage is what the completed row reports."""
    org, owner = _org_with_owner()
    client = _client_for(owner)

    body = _create_upload(client, org, size=1)
    file_id = body["file"]["id"]
    upload_url = body["upload_url"]

    requests.put(
        upload_url, data=io.BytesIO(_PDF_BYTES), headers={"Content-Type": "application/pdf"}
    )
    complete_response = client.post(f"/api/v1/orgs/{org.slug}/files/{file_id}/complete/")

    assert complete_response.status_code == 200
    assert complete_response.json()["size"] == len(_PDF_BYTES)


def test_deleting_a_pending_upload_is_rejected() -> None:
    org, owner = _org_with_owner()
    client = _client_for(owner)
    body = _create_upload(client, org)
    file_id = body["file"]["id"]

    response = client.delete(f"/api/v1/orgs/{org.slug}/files/{file_id}/")

    assert response.status_code == 409
    assert FileUpload.objects.get(pk=file_id).status == FileUpload.STATUS_PENDING


def test_deleting_an_already_deleted_upload_is_idempotent() -> None:
    org, owner = _org_with_owner()
    client = _client_for(owner)
    body = _create_upload(client, org)
    file_id = body["file"]["id"]
    upload_url = body["upload_url"]
    requests.put(
        upload_url, data=io.BytesIO(_PDF_BYTES), headers={"Content-Type": "application/pdf"}
    )
    client.post(f"/api/v1/orgs/{org.slug}/files/{file_id}/complete/")

    first = client.delete(f"/api/v1/orgs/{org.slug}/files/{file_id}/")
    second = client.delete(f"/api/v1/orgs/{org.slug}/files/{file_id}/")

    assert first.status_code == 204
    assert second.status_code == 204


def test_a_file_is_unreadable_from_a_different_organization() -> None:
    """The real cross-tenant test the acceptance criterion asks for —
    not an assertion that the object key merely *contains* the org id,
    but that a member of a different
    organisation gets a 404, the same "doesn't exist to you" response an
    absent row would produce."""
    org_a, owner_a = _org_with_owner()
    org_b, owner_b = _org_with_owner()

    body = _create_upload(_client_for(owner_a), org_a, filename="secret.pdf")
    file_id = body["file"]["id"]

    # Owner B is a legitimate owner of *their own* organisation — this
    # is not a permission-denied case, it's a does-not-exist-here case.
    cross_tenant_response = _client_for(owner_b).get(f"/api/v1/orgs/{org_b.slug}/files/{file_id}/")
    assert cross_tenant_response.status_code == 404

    # Confirming via org_a with an unrelated member is the actual owner path.
    same_org_response = _client_for(owner_a).get(f"/api/v1/orgs/{org_a.slug}/files/{file_id}/")
    assert same_org_response.status_code == 200


def test_a_suspended_member_cannot_create_an_upload() -> None:
    """``resolve_organization`` treats a suspended membership the same as
    no membership at all (PRD invariant 7: a 404 never discloses an
    organisation's existence to someone outside it) — so this is a 404,
    not a 403, same as the cross-tenant case above."""
    org, _owner = _org_with_owner()
    member = _add_member(org)
    Membership.objects.filter(organization=org, user=member).update(
        status=Membership.STATUS_SUSPENDED
    )

    response = client_post_create(_client_for(member), org)

    assert response.status_code == 404


def client_post_create(client: APIClient, org: Organization) -> Any:
    return client.post(
        f"/api/v1/orgs/{org.slug}/files/",
        {
            "filename": "x.pdf",
            "content_type": "application/pdf",
            "size": 1,
            "checksum_sha256": _PDF_SHA256,
        },
        content_type="application/json",
    )


def test_a_viewer_cannot_delete_a_file() -> None:
    """FILES_MANAGE, not FILES_VIEW, gates delete — a member holding
    only the view permission gets the same permission-denied shape as
    every other manage-gated action in this app. (The ``Member`` preset
    holds both codes — see keel/organizations/roles.py — so this builds
    a role with only FILES_VIEW directly, the same way
    ninja_tenant_isolation.py's meta-test does.)"""
    from keel.organizations.models import Role
    from keel.organizations.permissions import Perm

    org, owner = _org_with_owner()
    body = _create_upload(_client_for(owner), org)
    file_id = body["file"]["id"]

    viewer_role = Role.objects.create(name="_viewer_only", permissions=[Perm.FILES_VIEW])
    viewer = _user("viewer")
    Membership.objects.create(
        organization=org, user=viewer, role=viewer_role, status=Membership.STATUS_ACTIVE
    )

    response = _client_for(viewer).delete(f"/api/v1/orgs/{org.slug}/files/{file_id}/")

    assert response.status_code == 403

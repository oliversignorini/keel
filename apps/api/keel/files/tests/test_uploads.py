"""Presigned direct upload (PRD §5; docs/plans/phase-5.md 5.6). Uses
``moto``'s mocked S3 rather than a real MinIO/R2 — see
``keel.files.r2_client`` and ``infra/compose.dev.yml``'s ``minio``
service for the two real-environment stand-ins this project uses
instead of real R2 credentials, which don't exist."""

import io

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
    org = services.create_organization(name="Acme", slug=f"acme-{_counter}", created_by=owner)
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


def test_full_flow_presign_then_direct_upload_then_complete() -> None:
    org, owner = _org_with_owner()
    client = _client_for(owner)

    create_response = client.post(
        f"/api/v1/orgs/{org.slug}/files/",
        {"filename": "report.pdf", "content_type": "application/pdf", "size": 1234},
        content_type="application/json",
    )
    assert create_response.status_code == 201
    body = create_response.json()
    assert body["file"]["status"] == FileUpload.STATUS_PENDING
    file_id = body["file"]["id"]
    upload_url = body["upload_url"]
    assert str(org.pk) in FileUpload.objects.get(pk=file_id).key

    # "the browser uploads straight to R2" — done here with a plain PUT
    # against the presigned URL, exactly what a browser's fetch() would do.
    put_response = requests.put(
        upload_url, data=io.BytesIO(b"%PDF-1.4 fake"), headers={"Content-Type": "application/pdf"}
    )
    assert put_response.status_code == 200

    complete_response = client.post(f"/api/v1/orgs/{org.slug}/files/{file_id}/complete/")
    assert complete_response.status_code == 200
    assert complete_response.json()["status"] == FileUpload.STATUS_COMPLETE

    file_upload = FileUpload.objects.get(pk=file_id)
    assert file_upload.status == FileUpload.STATUS_COMPLETE


def test_complete_before_the_object_actually_exists_is_rejected() -> None:
    org, owner = _org_with_owner()
    client = _client_for(owner)

    create_response = client.post(
        f"/api/v1/orgs/{org.slug}/files/",
        {"filename": "report.pdf", "content_type": "application/pdf", "size": 1234},
        content_type="application/json",
    )
    file_id = create_response.json()["file"]["id"]

    complete_response = client.post(f"/api/v1/orgs/{org.slug}/files/{file_id}/complete/")

    assert complete_response.status_code == 422
    assert FileUpload.objects.get(pk=file_id).status == FileUpload.STATUS_PENDING


def test_a_file_is_unreadable_from_a_different_organization() -> None:
    """The real cross-tenant test the acceptance criterion asks for
    (docs/plans/phase-5.md 5.6) — not an assertion that the object key
    merely *contains* the org id, but that a member of a different
    organisation gets a 404, the same "doesn't exist to you" response an
    absent row would produce."""
    org_a, owner_a = _org_with_owner()
    org_b, owner_b = _org_with_owner()

    create_response = _client_for(owner_a).post(
        f"/api/v1/orgs/{org_a.slug}/files/",
        {"filename": "secret.pdf", "content_type": "application/pdf", "size": 1},
        content_type="application/json",
    )
    file_id = create_response.json()["file"]["id"]

    # Owner B is a legitimate owner of *their own* organisation — this
    # is not a permission-denied case, it's a does-not-exist-here case.
    cross_tenant_response = _client_for(owner_b).get(
        f"/api/v1/orgs/{org_b.slug}/files/{file_id}/"
    )
    assert cross_tenant_response.status_code == 404

    # Confirming via org_a with an unrelated member is the actual owner path.
    same_org_response = _client_for(owner_a).get(
        f"/api/v1/orgs/{org_a.slug}/files/{file_id}/"
    )
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

    response = _client_for(member).post(
        f"/api/v1/orgs/{org.slug}/files/",
        {"filename": "x.pdf", "content_type": "application/pdf", "size": 1},
        content_type="application/json",
    )

    assert response.status_code == 404

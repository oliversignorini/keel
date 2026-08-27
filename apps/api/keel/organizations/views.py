"""Views (PRD §7; phase-3.md B.3; phase-10.md 10.C).

``MembershipResource``/``RoleResource``/``InvitationResource`` declare
``required_permissions``, ``organization_scoped = True``, ``test_factory``
and ``detail_url_template`` — the tenant-isolation meta-test then walks
each automatically (PRD §4 invariant 7). The organisation itself has no
separate "row inside the org" to leak across tenants — resolving it *is*
the tenant boundary — so ``organization_detail``/``organization_transfer``
below call ``resolve_and_authorize`` directly rather than declaring an
``OrgScopedResource``, same reasoning as ``keel.billing.views``' plain
routes.

``invite_router`` uses ``optional_session_auth``: ``GET
/invite/<token>/`` must work signed-out (phase-3.md B.4 — the client
needs org name + locked email to drive signup before there's a session).
"""

from typing import Any

from django.http import Http404, HttpResponse
from django.utils import timezone
from ninja import Status

from keel.billing.entitlements import resolve_entitlements
from keel.core.exceptions import Conflict, NotAuthenticated, UnprocessableEntity
from keel.core.http_caching import set_reference_data_cache_headers
from keel.core.ninja_authz import (
    OrgScopedResource,
    keel_router,
    optional_auth_router,
    resolve_and_authorize,
)
from keel.core.ninja_pagination import Page, paginate
from keel.organizations import selectors, services
from keel.organizations.models import Invitation, Membership, Role
from keel.organizations.permissions import Perm
from keel.organizations.schemas import (
    InvitationCreateIn,
    InvitationOut,
    InviteDetailOut,
    MembershipOut,
    MembershipRoleUpdateIn,
    MeOut,
    OrganizationCreateIn,
    OrganizationOut,
    OrganizationUpdateIn,
    PermissionCodesOut,
    RoleOut,
    TransferIn,
    resolve_create_slug,
)


def _get_role_or_422(role_id: object) -> Role:
    role = Role.objects.filter(pk=str(role_id)).first()
    if role is None:
        raise UnprocessableEntity(code="role_not_found", message="Unknown role.")
    return role


# --- Organisations: list/create is not org-scoped; detail/transfer are ---
# reached through resolve_and_authorize directly, not an OrgScopedResource
# (module docstring).

org_router = keel_router(tags=["organizations"])


@org_router.get("/orgs/", response=Page[OrganizationOut], operation_id="listOrganizations")
def list_organizations(request: Any, cursor: str | None = None, limit: int | None = None) -> dict:
    queryset = selectors.list_organizations_for_user(request.auth)
    return paginate(request, queryset)


@org_router.post("/orgs/", response={201: OrganizationOut}, operation_id="createOrganization")
def create_organization(request: Any, payload: OrganizationCreateIn) -> Any:

    slug = resolve_create_slug(payload)
    organization = services.create_organization(
        created_by=request.auth, name=payload.name, slug=slug
    )
    return Status(201, organization)


@org_router.get("/orgs/{org_slug}/", response=OrganizationOut, operation_id="retrieveOrganization")
def organization_detail(request: Any, org_slug: str) -> Any:
    return resolve_and_authorize(request, org_slug, (Perm.ORG_VIEW,))


@org_router.patch("/orgs/{org_slug}/", response=OrganizationOut, operation_id="updateOrganization")
def organization_update(request: Any, org_slug: str, payload: OrganizationUpdateIn) -> Any:
    organization = resolve_and_authorize(request, org_slug, (Perm.ORG_UPDATE,))
    fields = payload.dict(exclude_unset=True)
    return services.update_organization(organization=organization, actor=request.auth, **fields)


@org_router.delete("/orgs/{org_slug}/", response={204: None}, operation_id="deleteOrganization")
def organization_delete(request: Any, org_slug: str) -> Any:

    organization = resolve_and_authorize(request, org_slug, (Perm.ORG_DELETE,))
    services.delete_organization(
        organization=organization,
        actor=request.auth,
        impersonator=getattr(request, "impersonator", None),
    )
    return Status(204, None)


@org_router.post(
    "/orgs/{org_slug}/transfer/", response=MembershipOut, operation_id="transferOrganization"
)
def organization_transfer(request: Any, org_slug: str, payload: TransferIn) -> Any:
    organization = resolve_and_authorize(request, org_slug, (Perm.ORG_TRANSFER,))
    to_membership_id = payload.membership_id
    from_membership = selectors.get_membership(user=request.auth, organization=organization)
    to_membership = (
        Membership.objects.filter(organization=organization, pk=to_membership_id)
        .select_related("role")
        .first()
    )
    if to_membership is None or from_membership is None:
        raise Conflict(code="membership_not_found", message="Target membership not found.")
    services.transfer_ownership(
        organization=organization,
        from_membership=from_membership,
        to_membership=to_membership,
        actor=request.auth,
    )
    return to_membership


# --- Members / roles / invitations: OrgScopedResources --------------------

nested_router = keel_router(tags=["organizations"])


class MembershipResource(OrgScopedResource):
    router = nested_router
    organization_scoped = True
    test_factory = "keel.organizations.tests.factories.membership_factory"
    required_permissions = (Perm.MEMBERS_VIEW,)
    detail_url_template = "/api/v1/orgs/{org_slug}/members/{id}/"


class RoleResource(OrgScopedResource):
    router = nested_router
    organization_scoped = True
    test_factory = "keel.organizations.tests.factories.role_factory"
    required_permissions = (Perm.MEMBERS_VIEW,)
    detail_url_template = "/api/v1/orgs/{org_slug}/roles/{id}/"


class InvitationResource(OrgScopedResource):
    router = nested_router
    organization_scoped = True
    test_factory = "keel.organizations.tests.factories.invitation_factory"
    required_permissions = (Perm.MEMBERS_INVITE,)
    detail_url_template = "/api/v1/orgs/{org_slug}/invitations/{id}/"


@nested_router.get("/{org_slug}/members/", response=Page[MembershipOut], operation_id="listMembers")
def list_members(
    request: Any, org_slug: str, cursor: str | None = None, limit: int | None = None
) -> dict:
    organization = resolve_and_authorize(request, org_slug, (Perm.MEMBERS_VIEW,))
    queryset = Membership.objects.select_related("user", "role").for_organization(organization)
    return paginate(request, queryset)


@nested_router.get(
    "/{org_slug}/members/{id}/", response=MembershipOut, operation_id="retrieveMember"
)
def retrieve_member(request: Any, org_slug: str, id: str) -> Any:
    organization = resolve_and_authorize(request, org_slug, (Perm.MEMBERS_VIEW,))
    membership = (
        Membership.objects.select_related("user", "role")
        .for_organization(organization)
        .filter(pk=id)
        .first()
    )
    if membership is None:
        raise Http404
    return membership


# PATCH only — same reasoning as keel.widgets.views.update_widget.
@nested_router.patch(
    "/{org_slug}/members/{id}/",
    response=MembershipOut,
    operation_id="updateMemberRole",
)
def update_member_role(
    request: Any, org_slug: str, id: str, payload: MembershipRoleUpdateIn
) -> Any:
    organization = resolve_and_authorize(request, org_slug, (Perm.MEMBERS_CHANGE_ROLE,))
    membership = Membership.objects.for_organization(organization).filter(pk=id).first()
    if membership is None:
        raise Http404
    role = _get_role_or_422(payload.role_id)
    return services.change_member_role(membership=membership, role=role, actor=request.auth)


@nested_router.delete(
    "/{org_slug}/members/{id}/", response={204: None}, operation_id="deleteMember"
)
def remove_member(request: Any, org_slug: str, id: str) -> Any:

    organization = resolve_and_authorize(request, org_slug, (Perm.MEMBERS_REMOVE,))
    membership = Membership.objects.for_organization(organization).filter(pk=id).first()
    if membership is None:
        raise Http404
    services.remove_member(membership=membership, actor=request.auth)
    return Status(204, None)


@nested_router.get("/{org_slug}/roles/", response=Page[RoleOut], operation_id="listRoles")
def list_roles(
    request: Any, org_slug: str, cursor: str | None = None, limit: int | None = None
) -> dict:
    organization = resolve_and_authorize(request, org_slug, (Perm.MEMBERS_VIEW,))
    queryset = selectors.list_roles_for_organization(organization)
    return paginate(request, queryset)


@nested_router.get("/{org_slug}/roles/{id}/", response=RoleOut, operation_id="retrieveRole")
def retrieve_role(request: Any, org_slug: str, id: str) -> Any:
    organization = resolve_and_authorize(request, org_slug, (Perm.MEMBERS_VIEW,))
    role = selectors.list_roles_for_organization(organization).filter(pk=id).first()
    if role is None:
        raise Http404
    return role


@nested_router.get(
    "/{org_slug}/invitations/", response=Page[InvitationOut], operation_id="listInvitations"
)
def list_invitations(
    request: Any, org_slug: str, cursor: str | None = None, limit: int | None = None
) -> dict:
    organization = resolve_and_authorize(request, org_slug, (Perm.MEMBERS_INVITE,))
    queryset = Invitation.objects.select_related("role", "invited_by").for_organization(
        organization
    )
    return paginate(request, queryset)


@nested_router.post(
    "/{org_slug}/invitations/", response={201: InvitationOut}, operation_id="createInvitation"
)
def create_invitation(request: Any, org_slug: str, payload: InvitationCreateIn) -> Any:

    organization = resolve_and_authorize(request, org_slug, (Perm.MEMBERS_INVITE,))
    role = _get_role_or_422(payload.role_id)
    invitation = services.create_invitation(
        organization=organization,
        email=payload.email,
        role=role,
        invited_by=request.auth,
    )
    return Status(201, invitation)


@nested_router.get(
    "/{org_slug}/invitations/{id}/", response=InvitationOut, operation_id="retrieveInvitation"
)
def retrieve_invitation(request: Any, org_slug: str, id: str) -> Any:
    organization = resolve_and_authorize(request, org_slug, (Perm.MEMBERS_INVITE,))
    invitation = (
        Invitation.objects.select_related("role", "invited_by")
        .for_organization(organization)
        .filter(pk=id)
        .first()
    )
    if invitation is None:
        raise Http404
    return invitation


@nested_router.delete(
    "/{org_slug}/invitations/{id}/", response={204: None}, operation_id="deleteInvitation"
)
def revoke_invitation(request: Any, org_slug: str, id: str) -> Any:

    organization = resolve_and_authorize(request, org_slug, (Perm.MEMBERS_INVITE,))
    invitation = Invitation.objects.for_organization(organization).filter(pk=id).first()
    if invitation is None:
        raise Http404
    services.revoke_invitation(invitation=invitation, actor=request.auth)
    return Status(204, None)


# --- /me/ and /permissions/: global, authenticated ------------------------

me_router = keel_router(tags=["me"])


@me_router.get("/me/", response=MeOut, operation_id="retrieveMe")
def me(request: Any) -> dict:
    user = request.auth
    organizations: list[dict[str, Any]] = []
    for organization in selectors.list_organizations_for_user(user):
        membership = selectors.get_membership(user=user, organization=organization)
        organizations.append(
            {
                "id": str(organization.id),
                "slug": organization.slug,
                "name": organization.name,
                "role": membership.role.name if membership else None,
                "permissions": selectors.resolve_permission_codes(membership),
                "entitlements": resolve_entitlements(organization),
            }
        )
    impersonator = getattr(request, "impersonator", None)
    return {
        "user": {"id": str(user.id), "email": user.email, "name": user.name},
        "organizations": organizations,
        "impersonator": (
            {"id": str(impersonator.id), "email": impersonator.email, "name": impersonator.name}
            if impersonator is not None
            else None
        ),
    }


@me_router.get("/permissions/", response=PermissionCodesOut, operation_id="retrievePermissionCodes")
def permissions_registry(request: Any, response: HttpResponse) -> dict:
    """A Reference Data Holder (api-patterns finding 13) — the permission
    registry only changes on deploy, not per-request."""
    codes = selectors.registered_permission_codes()
    set_reference_data_cache_headers(response, sorted(codes))
    return {"codes": codes}


# --- /invite/<token>/: public GET, authenticated POST ----------------------

invite_router = optional_auth_router()


def _resolve_valid_invitation(token: str) -> Invitation:
    invitation = selectors.get_invitation_by_token(token)
    if (
        invitation is None
        or invitation.revoked_at is not None
        or invitation.accepted_at is not None
        or invitation.expires_at <= timezone.now()
    ):
        raise Conflict(code="invalid_or_expired", message="This invitation is no longer valid.")
    return invitation


@invite_router.get("/invite/{token}/", response=InviteDetailOut, operation_id="retrieveInvite")
def invite_detail(request: Any, token: str) -> dict:
    invitation = _resolve_valid_invitation(token)
    return {
        "organization": {
            "name": invitation.organization.name,
            "slug": invitation.organization.slug,
        },
        "email": invitation.email,
        "requires_signup": not request.auth.is_authenticated,
    }


@invite_router.post("/invite/{token}/", response=MembershipOut, operation_id="acceptInvite")
def invite_accept(request: Any, token: str) -> Any:
    if not request.auth.is_authenticated:
        raise NotAuthenticated()
    invitation = _resolve_valid_invitation(token)
    if invitation.email.lower() != request.auth.email.lower():
        # Wrong email: rejected without disclosing who was actually
        # invited (phase-3.md B.4).
        raise Conflict(code="invalid_or_expired", message="This invitation is no longer valid.")
    return services.accept_invitation(invitation=invitation, user=request.auth)

"""Viewsets (PRD §7; phase-3.md B.3).

Every ``organization_scoped`` viewset declares ``required_permissions``,
``organization_scoped = True`` and ``test_factory`` — enforced at import
time by ``keel.core.authz`` (PRD §4 invariant 7). The organisation itself
has no separate "row inside the org" to leak across tenants — resolving
it *is* the tenant boundary — so ``OrganizationDetailView`` below is a
plain view rather than an ``OrgScopedViewSet``; see its docstring.
"""

from typing import Any, ClassVar

from django.http import Http404
from django.utils import timezone
from rest_framework import generics, mixins, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from keel.core.authz import OrgScopedViewSet, has_perm
from keel.core.exceptions import Conflict, PermissionDeniedWithReason
from keel.organizations import selectors, services
from keel.organizations.models import Invitation, Membership, Organization
from keel.organizations.permissions import Perm
from keel.organizations.resolvers import resolve_organization
from keel.organizations.serializers import (
    InvitationCreateSerializer,
    InvitationSerializer,
    MembershipRoleUpdateSerializer,
    MembershipSerializer,
    OrganizationCreateSerializer,
    OrganizationSerializer,
    OrganizationUpdateSerializer,
    RoleSerializer,
)


class OrganizationListCreateView(generics.ListCreateAPIView):
    """``/organizations/`` — list the caller's organisations, or create a
    new one. Not tenant-scoped: there is no organisation in the URL to
    resolve yet (PRD §4, org creation happens before tenant context
    exists), so this deliberately does not use ``OrgScopedViewSet``."""

    permission_classes = (IsAuthenticated,)
    serializer_class = OrganizationSerializer

    def get_queryset(self) -> Any:
        return selectors.list_organizations_for_user(self.request.user)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = OrganizationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = services.create_organization(
            created_by=request.user, **serializer.validated_data
        )
        return Response(
            OrganizationSerializer(organization).data, status=status.HTTP_201_CREATED
        )


class OrganizationDetailView(APIView):
    """``/organizations/<org_slug>/`` — retrieve, update, or delete a
    single organisation.

    Resolving ``org_slug`` *is* the tenant boundary here (there is no
    separate row inside the organisation that could leak to another
    tenant the way a ``Membership`` or ``Invitation`` row could), so this
    calls the same resolver ``OrgScopedViewSet`` uses directly rather than
    inheriting it — a non-member and a nonexistent slug both 404 (PRD §6).
    """

    permission_classes = (IsAuthenticated,)

    def _get_organization(self, request: Request, org_slug: str) -> Organization:
        organization = resolve_organization(request, org_slug)
        if organization is None:
            raise Http404
        return organization

    def _require(self, request: Request, organization: Organization, code: str) -> None:
        decision = has_perm(request.user, organization, code)
        if not decision.allowed:
            raise PermissionDeniedWithReason(
                code=decision.reason or "permission_denied", details=decision.details
            )

    def get(self, request: Request, org_slug: str) -> Response:
        organization = self._get_organization(request, org_slug)
        self._require(request, organization, Perm.ORG_VIEW)
        return Response(OrganizationSerializer(organization).data)

    def patch(self, request: Request, org_slug: str) -> Response:
        organization = self._get_organization(request, org_slug)
        self._require(request, organization, Perm.ORG_UPDATE)
        serializer = OrganizationUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        organization = services.update_organization(
            organization=organization, actor=request.user, **serializer.validated_data
        )
        return Response(OrganizationSerializer(organization).data)

    def delete(self, request: Request, org_slug: str) -> Response:
        organization = self._get_organization(request, org_slug)
        self._require(request, organization, Perm.ORG_DELETE)
        services.delete_organization(organization=organization, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class OrganizationTransferView(APIView):
    """``POST /organizations/<org_slug>/transfer/`` — hand ownership to
    another active member."""

    permission_classes = (IsAuthenticated,)

    def post(self, request: Request, org_slug: str) -> Response:
        organization = resolve_organization(request, org_slug)
        if organization is None:
            raise Http404
        decision = has_perm(request.user, organization, Perm.ORG_TRANSFER)
        if not decision.allowed:
            raise PermissionDeniedWithReason(
                code=decision.reason or "permission_denied", details=decision.details
            )
        to_membership_id = request.data.get("membership_id")
        from_membership = selectors.get_membership(user=request.user, organization=organization)
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
            actor=request.user,
        )
        return Response(MembershipSerializer(to_membership).data)


class MembershipViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    OrgScopedViewSet,
):
    """``/organizations/<org_slug>/members/``."""

    queryset = Membership.objects.select_related("user", "role")
    serializer_class = MembershipSerializer
    organization_scoped = True
    test_factory = "keel.organizations.tests.factories.membership_factory"

    # The class-level default doubles as what the cross-org meta-test
    # checks (it only ever exercises `retrieve`) — keep it in sync with
    # _ACTION_PERMISSIONS["retrieve"]. Per-request dispatch happens in
    # initial(): required_permissions must be a plain tuple readable off
    # the *class* (not a property), because assert_cross_org_404 reads
    # `viewset_cls.required_permissions` directly (PRD §4 invariant 7).
    required_permissions: tuple[str, ...] = (Perm.MEMBERS_VIEW,)

    _ACTION_PERMISSIONS: ClassVar[dict[str, tuple[str, ...]]] = {
        "list": (Perm.MEMBERS_VIEW,),
        "retrieve": (Perm.MEMBERS_VIEW,),
        "update": (Perm.MEMBERS_CHANGE_ROLE,),
        "partial_update": (Perm.MEMBERS_CHANGE_ROLE,),
        "destroy": (Perm.MEMBERS_REMOVE,),
    }

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        self.required_permissions = self._ACTION_PERMISSIONS.get(
            self.action, self.required_permissions
        )
        super().initial(request, *args, **kwargs)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        membership = self.get_object()
        serializer = MembershipRoleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = services.change_member_role(
            membership=membership, role=serializer.validated_data["role_id"], actor=request.user
        )
        return Response(MembershipSerializer(membership).data)

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self.update(request, *args, **kwargs)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        membership = self.get_object()
        services.remove_member(membership=membership, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RoleViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, OrgScopedViewSet):
    """``/organizations/<org_slug>/roles/`` — read-only: the three global
    presets plus any custom roles belonging to the organisation."""

    serializer_class = RoleSerializer
    organization_scoped = True
    required_permissions = (Perm.MEMBERS_VIEW,)
    test_factory = "keel.organizations.tests.factories.role_factory"

    def get_queryset(self) -> Any:
        # Deliberately bypasses OrgScopedViewSet.get_queryset(): Role isn't
        # an OrgScopedModel (a preset's organization is None by design —
        # see models.py), so the generic `.for_organization()` filter
        # doesn't apply here.
        return selectors.list_roles_for_organization(self.organization)


class InvitationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    OrgScopedViewSet,
):
    """``/organizations/<org_slug>/invitations/``."""

    queryset = Invitation.objects.select_related("role", "invited_by")
    serializer_class = InvitationSerializer
    organization_scoped = True
    required_permissions = (Perm.MEMBERS_INVITE,)
    test_factory = "keel.organizations.tests.factories.invitation_factory"

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = InvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = services.create_invitation(
            organization=self.organization,
            email=serializer.validated_data["email"],
            role=serializer.validated_data["role_id"],
            invited_by=request.user,
        )
        return Response(InvitationSerializer(invitation).data, status=status.HTTP_201_CREATED)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        invitation = self.get_object()
        services.revoke_invitation(invitation=invitation, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """``GET /me/`` — user, organisations, current role, resolved
    permission codes per organisation (PRD §7). Entitlement resolution is
    Phase 4's; the ``entitlements`` seam is left as an empty dict per
    organisation until then."""

    permission_classes = (IsAuthenticated,)

    def get(self, request: Request) -> Response:
        user = request.user
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
                    "entitlements": {},
                }
            )
        return Response(
            {
                "user": {"id": str(user.id), "email": user.email, "name": user.name},
                "organizations": organizations,
            }
        )


class PermissionsRegistryView(APIView):
    """``GET /permissions/`` — the full permission-code registry, for the
    role editor (PRD §7). Global: identical for every caller, not
    tenant-scoped data."""

    permission_classes = (IsAuthenticated,)

    def get(self, request: Request) -> Response:
        return Response({"codes": selectors.registered_permission_codes()})


class InvitationAcceptView(APIView):
    """``/invite/<token>/`` (PRD §6 "Invitation"; phase-3.md B.4). All four
    edge cases: wrong email rejected without disclosing the invitee;
    expired and revoked indistinguishable to the recipient; not signed in
    returns enough to drive signup with a locked email; signed in with a
    matching email accepts."""

    def get_permissions(self) -> list[Any]:
        # GET must work signed-out — that's the "not signed in" case
        # (phase-3.md B.4): the client needs org name + locked email to
        # drive signup before there's any session to authenticate.
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    def _resolve_valid(self, token: str) -> Invitation:
        invitation = selectors.get_invitation_by_token(token)
        if (
            invitation is None
            or invitation.revoked_at is not None
            or invitation.accepted_at is not None
            or invitation.expires_at <= timezone.now()
        ):
            # Expired, revoked, and nonexistent are all "invalid_or_expired"
            # — the recipient cannot distinguish them (phase-3.md B.4).
            raise Conflict(
                code="invalid_or_expired", message="This invitation is no longer valid."
            )
        return invitation

    def get(self, request: Request, token: str) -> Response:
        invitation = self._resolve_valid(token)
        return Response(
            {
                "organization": {
                    "name": invitation.organization.name,
                    "slug": invitation.organization.slug,
                },
                "email": invitation.email,
                "requires_signup": not request.user.is_authenticated,
            }
        )

    def post(self, request: Request, token: str) -> Response:
        invitation = self._resolve_valid(token)
        if invitation.email.lower() != request.user.email.lower():
            # Wrong email: rejected without disclosing who was actually
            # invited (phase-3.md B.4).
            raise Conflict(
                code="invalid_or_expired", message="This invitation is no longer valid."
            )
        membership = services.accept_invitation(invitation=invitation, user=request.user)
        return Response(MembershipSerializer(membership).data)

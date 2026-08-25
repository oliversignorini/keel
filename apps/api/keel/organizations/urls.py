"""URL wiring (PRD §7). Also builds the combined ``.registry`` that
``settings.KEEL_API_ROUTER`` points at, so ``keel.core.authz``'s
router-wiring meta-test can walk every ``organization_scoped`` viewset
registered here (PRD §4 invariant 7)."""

from typing import Any

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from keel.organizations import viewsets

nested_router = SimpleRouter(trailing_slash=True)
nested_router.register("members", viewsets.MembershipViewSet, basename="membership")
nested_router.register("roles", viewsets.RoleViewSet, basename="role")
nested_router.register("invitations", viewsets.InvitationViewSet, basename="invitation")


class _CombinedRegistry:
    """Exposes ``.registry`` the way a DRF router does — the shape
    ``iter_org_scoped_viewsets`` / ``iter_global_justifications`` expect —
    without needing a single flat router to also produce the actually
    nested URLs below."""

    def __init__(self, *routers: Any) -> None:
        self.registry = [entry for router in routers for entry in router.registry]


api_registry = _CombinedRegistry(nested_router)

urlpatterns = [
    path("organizations/", viewsets.OrganizationListCreateView.as_view(), name="organization-list"),
    path(
        "organizations/<slug:org_slug>/",
        viewsets.OrganizationDetailView.as_view(),
        name="organization-detail",
    ),
    path(
        "organizations/<slug:org_slug>/transfer/",
        viewsets.OrganizationTransferView.as_view(),
        name="organization-transfer",
    ),
    path("organizations/<slug:org_slug>/", include(nested_router.urls)),
    path("me/", viewsets.MeView.as_view(), name="me"),
    path("permissions/", viewsets.PermissionsRegistryView.as_view(), name="permissions"),
    path("invite/<str:token>/", viewsets.InvitationAcceptView.as_view(), name="invite-accept"),
]

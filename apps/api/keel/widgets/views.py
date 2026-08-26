"""Views (PRD §7; docs/plans/phase-6.md 6.D). THIN: parse, call service,
serialize, return. Declares ``required_permissions``,
``organization_scoped = True`` and ``test_factory`` — the tenant-isolation
meta-test then walks this viewset automatically (PRD §4 invariant 7).
"""

from typing import Any, ClassVar

from rest_framework import mixins, status
from rest_framework.request import Request
from rest_framework.response import Response

from keel.core.authz import OrgScopedViewSet
from keel.organizations.permissions import Perm
from keel.widgets import selectors, services
from keel.widgets.models import Widget
from keel.widgets.serializers import WidgetSerializer, WidgetUpdateSerializer, WidgetWriteSerializer


class WidgetViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    OrgScopedViewSet,
):
    """``/organizations/<org_slug>/widgets/`` — the reference-slice CRUD
    endpoint (PRD §7's demo-resource route table)."""

    queryset = Widget.objects.select_related("created_by")
    serializer_class = WidgetSerializer
    organization_scoped = True
    test_factory = "keel.widgets.tests.factories.widget_factory"

    # Matches _ACTION_PERMISSIONS["retrieve"] — the meta-test only ever
    # exercises retrieve, and reads required_permissions off the class
    # (PRD §4 invariant 7), same convention as MembershipViewSet.
    required_permissions: tuple[str, ...] = (Perm.WIDGETS_VIEW,)

    _ACTION_PERMISSIONS: ClassVar[dict[str, tuple[str, ...]]] = {
        "list": (Perm.WIDGETS_VIEW,),
        "retrieve": (Perm.WIDGETS_VIEW,),
        "create": (Perm.WIDGETS_MANAGE,),
        "update": (Perm.WIDGETS_MANAGE,),
        "partial_update": (Perm.WIDGETS_MANAGE,),
        "destroy": (Perm.WIDGETS_MANAGE,),
    }

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        self.required_permissions = self._ACTION_PERMISSIONS.get(
            self.action, self.required_permissions
        )
        super().initial(request, *args, **kwargs)

    def get_queryset(self) -> Any:
        return selectors.list_widgets(self.organization)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = WidgetWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        widget = services.create_widget(
            organization=self.organization, created_by=request.user, **serializer.validated_data
        )
        return Response(WidgetSerializer(widget).data, status=status.HTTP_201_CREATED)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        widget = self.get_object()
        partial = kwargs.pop("partial", False)
        serializer = WidgetUpdateSerializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        widget = services.update_widget(
            widget=widget,
            actor=request.user,
            impersonator=getattr(request, "impersonator", None),
            **serializer.validated_data,
        )
        return Response(WidgetSerializer(widget).data)

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        widget = self.get_object()
        services.delete_widget(
            widget=widget, actor=request.user, impersonator=getattr(request, "impersonator", None)
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

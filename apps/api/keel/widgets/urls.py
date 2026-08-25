"""URL wiring (PRD §7). ``widgets_router`` is imported into
``keel.organizations.urls``'s ``api_registry`` so the tenant-isolation
meta-test's router walk (PRD §4 invariant 7) reaches ``WidgetViewSet``."""

from rest_framework.routers import SimpleRouter

from keel.widgets import views

widgets_router = SimpleRouter(trailing_slash=True)
widgets_router.register("widgets", views.WidgetViewSet, basename="widget")

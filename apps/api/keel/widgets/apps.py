from django.apps import AppConfig


class WidgetsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "keel.widgets"

    def ready(self) -> None:
        # Registers "widgets" as a countable resource for
        # keel.billing.entitlements.check_limit (docs/plans/phase-4.md
        # B.4) — the demo resource /new-resource copies from, deleted
        # along with this app's other files by `init`.
        from keel.billing.entitlements import register_resource_counter
        from keel.widgets.models import Widget

        register_resource_counter(
            "widgets",
            lambda organization: Widget.objects.filter(organization=organization).count(),
        )

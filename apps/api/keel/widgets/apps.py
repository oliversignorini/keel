from django.apps import AppConfig


class WidgetsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "keel.widgets"

    def ready(self) -> None:
        # Registers "widgets" as a countable resource for
        # keel.billing.entitlements.check_limit (docs/plans/phase-4.md
        # B.4). check_limit raises UnregisteredResource for a name nobody
        # registered a counter for, so this has to exist before any
        # service calls it — hence AppConfig.ready(), not import time.
        from keel.billing.entitlements import register_resource_counter
        from keel.widgets.models import Widget

        register_resource_counter(
            "widgets",
            lambda organization: Widget.objects.filter(organization=organization).count(),
        )

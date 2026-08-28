from django.apps import AppConfig


class __Resources__Config(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "keel.__app__"

    def ready(self) -> None:
        # Registers "__app__" as a countable resource for
        # keel.billing.entitlements.check_limit (docs/plans/phase-4.md
        # B.4). check_limit raises UnregisteredResource for a name nobody
        # registered a counter for, so this has to exist before any
        # service calls it — hence AppConfig.ready(), not import time.
        from keel.__app__.models import __Resource__
        from keel.billing.entitlements import register_resource_counter

        register_resource_counter(
            "__app__",
            lambda organization: __Resource__.objects.filter(organization=organization).count(),
        )

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "keel.core"

    def ready(self) -> None:
        from keel.core import checks  # noqa: F401 — registers via @register()

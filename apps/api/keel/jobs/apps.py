from django.apps import AppConfig


class JobsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "keel.jobs"

    def ready(self) -> None:
        from keel.jobs import demo  # noqa: F401 — registers the demo job type

from django.apps import AppConfig


class OrganizationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "keel.organizations"

    def ready(self) -> None:
        # Registers every Perm code's guard against keel.core.authz.registry
        # (PRD §4 invariant 2) — import only, no side effects beyond that.
        from keel.organizations import permissions  # noqa: F401

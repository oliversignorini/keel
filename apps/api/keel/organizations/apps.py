from django.apps import AppConfig


class OrganizationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "keel.organizations"

    def ready(self) -> None:
        # Registers every Perm code's guard against keel.core.authz.registry
        # (PRD §4 invariant 2) — import only, no side effects beyond that.
        # "seats" is the one resource keel.billing.entitlements always
        # knows about regardless of which domain apps a project keeps
        # (docs/plans/phase-4.md B.4) — active membership count is the
        # natural seat usage for any plan that declares a "seats" limit.
        from keel.billing.entitlements import register_resource_counter
        from keel.organizations import permissions  # noqa: F401
        from keel.organizations.models import Membership

        register_resource_counter(
            "seats",
            lambda organization: Membership.objects.filter(
                organization=organization, status=Membership.STATUS_ACTIVE
            ).count(),
        )

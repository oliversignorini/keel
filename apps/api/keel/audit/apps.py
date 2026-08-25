from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "keel.audit"

    def ready(self) -> None:
        # Installs the real AuditLog writer against keel.core.audit's
        # recorder seam (PRD v1.2 §8 Phase 8; docs/plans/phase-8.md 8.1).
        # Every @audited service call is a no-op until this runs.
        from keel.audit.recorder import record_audit_event
        from keel.core import audit

        audit.set_recorder(record_audit_event)

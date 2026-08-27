from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from keel.audit.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Append-only, same discipline as ``CreditLedgerEntryAdmin``
    (ddia#19): a log a staff user can edit or delete through the admin —
    including rows recording their own actions — is not a log."""

    list_display = ("action", "organization", "actor", "target_type", "created_at")
    list_filter = ("action",)
    search_fields = ("organization__name", "target_type", "target_id")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

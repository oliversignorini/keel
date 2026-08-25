from django.contrib import admin

from keel.connections.models import Connection


@admin.register(Connection)
class ConnectionAdmin(admin.ModelAdmin):
    # access_token / refresh_token are excluded entirely — there is no
    # view in which they are legitimately readable (PRD, "Third-party
    # OAuth connections").
    list_display = ("provider", "external_account", "organization", "status", "expires_at")
    list_filter = ("provider", "status")
    search_fields = ("external_account", "organization__name")
    fields = (
        "organization",
        "provider",
        "external_account",
        "scopes",
        "status",
        "connected_by",
        "expires_at",
        "created_at",
        "updated_at",
    )
    readonly_fields = ("created_at", "updated_at")

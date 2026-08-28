from typing import cast

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect

from keel.accounts.models import User
from keel.audit.models import AuditLog
from keel.core.impersonation import start_impersonation


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("email",)
    list_display = ("email", "name", "is_staff", "is_active")
    search_fields = ("email", "name")
    actions = ("impersonate",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("name", "avatar_url")}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )
    readonly_fields = ("date_joined",)

    @admin.action(description="Impersonate this user")
    def impersonate(self, request: HttpRequest, queryset: QuerySet[User]) -> HttpResponse | None:
        """Staff-only (PRD §6 "Impersonation"):
        Django admin's own permission check already required ``is_staff``
        to reach this action at all. Logs the browser session in as the
        selected user, writes ``impersonation.start`` recording both
        users, and redirects into the app frontend — where
        ``<ImpersonationBanner>`` picks the state up from ``/me/``."""
        if queryset.count() != 1:
            self.message_user(
                request, "Select exactly one user to impersonate.", level=messages.ERROR
            )
            return None
        target = queryset.first()
        assert target is not None
        # Captured before start_impersonation() calls django.contrib.auth.
        # login(), which rebinds request.user to target — using
        # request.user for the audit row after that point would silently
        # record the impersonator as themselves.
        impersonator = cast(User, request.user)
        if target.pk == impersonator.pk:
            self.message_user(request, "You cannot impersonate yourself.", level=messages.ERROR)
            return None

        start_impersonation(request, impersonator=impersonator, target=target)
        AuditLog.objects.create(
            actor=target,
            impersonator=impersonator,
            action="impersonation.start",
            target_type="User",
            target_id=str(target.pk),
        )
        self.message_user(request, f"Now impersonating {target.email}.", level=messages.SUCCESS)
        return HttpResponseRedirect(settings.APP_FRONTEND_URL)

from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from keel.core.tasks import redrive
from keel.jobs.models import FailedTask, Job, JobArtifact, JobStep

admin.site.register(Job)
admin.site.register(JobStep)
admin.site.register(JobArtifact)


@admin.register(FailedTask)
class FailedTaskAdmin(admin.ModelAdmin):
    """Re-drivable from Django admin (PRD §5; docs/plans/phase-5.md 5.3)."""

    list_display = ("task_name", "attempts", "created_at", "redriven_at")
    list_filter = ("task_name",)
    readonly_fields = ("task_name", "args", "error", "traceback", "attempts", "created_at")
    actions = ("redrive_selected",)

    @admin.action(description="Redrive selected failed tasks")
    def redrive_selected(self, request: HttpRequest, queryset: Any) -> None:
        for failed_task in queryset:
            redrive(failed_task.pk)
        self.message_user(request, f"Redrove {queryset.count()} task(s).")

from django.contrib import admin

from keel.jobs.models import FailedTask, Job, JobStep

admin.site.register(Job)
admin.site.register(JobStep)
# FailedTask admin actions (redrive) are Phase 5's territory; this phase
# only registers it for inspection.
admin.site.register(FailedTask)

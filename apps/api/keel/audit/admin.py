from django.contrib import admin

from keel.audit.models import AuditLog

admin.site.register(AuditLog)

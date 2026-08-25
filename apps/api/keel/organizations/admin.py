from django.contrib import admin

from keel.organizations.models import Invitation, Membership, Organization, Role

admin.site.register(Organization)
admin.site.register(Role)
admin.site.register(Membership)
admin.site.register(Invitation)

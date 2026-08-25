from django.urls import path

from keel.audit.views import ImpersonationExitView

urlpatterns = [
    path("impersonation/exit/", ImpersonationExitView.as_view(), name="impersonation-exit"),
]

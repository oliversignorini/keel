"""Django admin for billing (PRD §4 "Data model"; docs/plans/phase-4.md
A.4). ``CreditLedgerEntry`` is append-only, so its admin is read-only —
the sole way an adjustment entry gets written is
``keel.billing.credits.adjust``, reached here through
``CreditBalanceAdmin``'s "Adjust balance" action, which requires a
reason and records the acting operator as the actor before delegating.
"""

from typing import Any

from django import forms
from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import URLPattern, path, reverse

from keel.billing import credits
from keel.billing.models import (
    CreditBalance,
    CreditLedgerEntry,
    Plan,
    Price,
    StripeEvent,
    Subscription,
)
from keel.core.exceptions import PaymentRequired

admin.site.register(Plan)
admin.site.register(Price)
admin.site.register(Subscription)
admin.site.register(StripeEvent)


@admin.register(CreditLedgerEntry)
class CreditLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("organization", "kind", "amount", "job", "actor", "created_at")
    list_filter = ("kind",)
    search_fields = ("organization__name", "reason")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


class AdjustmentForm(forms.Form):
    amount = forms.IntegerField(help_text="Positive to credit, negative to debit. Cannot be zero.")
    reason = forms.CharField(widget=forms.Textarea)

    def clean_amount(self) -> int:
        amount: int = self.cleaned_data["amount"]
        if amount == 0:
            raise forms.ValidationError("Adjustment amount must be non-zero.")
        return amount


@admin.register(CreditBalance)
class CreditBalanceAdmin(admin.ModelAdmin):
    list_display = ("organization", "balance", "updated_at")
    readonly_fields = ("balance", "updated_at")
    search_fields = ("organization__name",)
    change_form_template = "admin/billing/creditbalance/change_form.html"

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def get_urls(self) -> list[URLPattern]:
        custom = [
            path(
                "<path:object_id>/adjust/",
                self.admin_site.admin_view(self.adjust_view),
                name="billing_creditbalance_adjust",
            ),
        ]
        return custom + super().get_urls()

    def adjust_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        balance_row = self.get_object(request, object_id)
        if balance_row is None or not self.has_change_permission(request, balance_row):
            self.message_user(request, "Not found or not permitted.", level=messages.ERROR)
            return redirect("admin:billing_creditbalance_changelist")

        if request.method == "POST":
            form = AdjustmentForm(request.POST)
            if form.is_valid():
                try:
                    credits.adjust(
                        balance_row.organization,
                        form.cleaned_data["amount"],
                        reason=form.cleaned_data["reason"],
                        actor=request.user,
                    )
                except PaymentRequired as exc:
                    self.message_user(request, exc.message, level=messages.ERROR)
                else:
                    self.message_user(request, "Adjustment recorded.", level=messages.SUCCESS)
                    return redirect(reverse("admin:billing_creditbalance_change", args=[object_id]))
        else:
            form = AdjustmentForm()

        context = {
            **self.admin_site.each_context(request),
            "title": f"Adjust credit balance — {balance_row.organization}",
            "form": form,
            "original": balance_row,
            "opts": self.model._meta,
        }
        return render(request, "admin/billing/creditbalance/adjust.html", context)

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        extra_context = extra_context or {}
        extra_context["adjust_url"] = reverse(
            "admin:billing_creditbalance_adjust", args=[object_id]
        )
        return super().change_view(request, object_id, form_url, extra_context)

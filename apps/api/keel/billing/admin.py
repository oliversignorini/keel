from django.contrib import admin

from keel.billing.models import (
    CreditBalance,
    CreditLedgerEntry,
    Plan,
    Price,
    StripeEvent,
    Subscription,
)

admin.site.register(Plan)
admin.site.register(Price)
admin.site.register(Subscription)
admin.site.register(StripeEvent)
admin.site.register(CreditLedgerEntry)
admin.site.register(CreditBalance)

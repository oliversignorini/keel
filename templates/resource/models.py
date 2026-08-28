"""__Resource__ — data shape only (PRD §4 "Data model"; CLAUDE.md's
per-app file shape). No queries and no business rules: reads live in
``selectors.py``, writes in ``services.py``.

Constraints, extra indexes, nullability and every other ``Meta`` option
are judgement rather than mechanics, and the generator deliberately stops
short of them (ADR 0004, "Full codegen, delete the commands"). Add them
here and write the migration with ``makemigrations``.
"""

from django.db import models

from keel.core.models import OrgScopedModel


class __Resource__(OrgScopedModel):
    # keel:insert model_fields
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="__resources___created"
    )

    class Meta:
        indexes = (models.Index(fields=["organization", "created_at"]),)

    # keel:insert model_str

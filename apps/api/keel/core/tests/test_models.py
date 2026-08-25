from django.db import models
from django.test.utils import isolate_apps

from keel.core.models import OrgScopedModel, OrgScopedQuerySet, SoftDeleteModel, TimestampedModel


def test_timestamped_model_is_abstract() -> None:
    assert TimestampedModel._meta.abstract is True


@isolate_apps("keel.core")
def test_timestamped_model_has_created_and_updated_at() -> None:
    class TimestampedThing(TimestampedModel):
        class Meta:
            app_label = "core"

    field_names = {f.name for f in TimestampedThing._meta.get_fields()}

    assert "created_at" in field_names
    assert "updated_at" in field_names


def test_org_scoped_model_is_abstract() -> None:
    assert OrgScopedModel._meta.abstract is True


@isolate_apps("keel.core")
def test_org_scoped_model_has_organization_fk() -> None:
    class OrgScopedThing(OrgScopedModel):
        class Meta:
            app_label = "core"

    field = OrgScopedThing._meta.get_field("organization")

    assert field.is_relation
    assert field.many_to_one


@isolate_apps("keel.core")
def test_org_scoped_model_organization_field_is_indexed() -> None:
    class OrgScopedThing(OrgScopedModel):
        class Meta:
            app_label = "core"

    field = OrgScopedThing._meta.get_field("organization")

    assert getattr(field, "db_index", False) or any(
        "organization" in idx.fields for idx in OrgScopedThing._meta.indexes
    )


@isolate_apps("keel.core")
def test_org_scoped_model_uses_org_scoped_queryset_manager() -> None:
    class OrgScopedThing(OrgScopedModel):
        class Meta:
            app_label = "core"

    assert isinstance(OrgScopedThing.objects.none(), models.QuerySet)
    assert hasattr(OrgScopedThing.objects, "for_organization")


@isolate_apps("keel.core")
def test_org_scoped_queryset_for_organization_filters() -> None:
    class OrgScopedThing(OrgScopedModel):
        class Meta:
            app_label = "core"

    qs = OrgScopedThing.objects.none()

    assert isinstance(qs, OrgScopedQuerySet)


def test_soft_delete_model_is_abstract() -> None:
    assert SoftDeleteModel._meta.abstract is True


@isolate_apps("keel.core")
def test_soft_delete_model_has_deleted_at() -> None:
    class SoftDeleteThing(SoftDeleteModel):
        class Meta:
            app_label = "core"

    field = SoftDeleteThing._meta.get_field("deleted_at")

    assert field.null is True


# Behavioural coverage of for_organization() against a real Organization
# row lives in keel.widgets.tests.test_models (task 1.10) — OrgScopedModel's
# "organization" FK is a string reference to "organizations.Organization"
# precisely so keel.core never imports keel.organizations, which means it
# can't be resolved and queried against until that model exists.

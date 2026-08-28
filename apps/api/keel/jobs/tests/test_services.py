"""``create_job`` / ``cancel_job`` (PRD §5.5.3 idempotency, §4 credits)."""

from unittest.mock import patch

import pytest
from django.db import IntegrityError

from keel.billing import credits
from keel.billing.models import CreditLedgerEntry
from keel.billing.tests.factories import make_organization, make_user
from keel.core.exceptions import PaymentRequired, UnprocessableEntity
from keel.jobs import services
from keel.jobs.demo import DEMO_JOB_TYPE
from keel.jobs.models import Job

# BILLING_CREDITS pinned off, not inherited from the environment: these
# are tests of the generic job machinery, and they only ever passed with
# credits enabled by coincidence of the shipped .env.example default —
# an instantiation that turns credits on (scripts/init.ts billing=both)
# surfaced that as 402s from unfunded organisations (template-ci run,
# 28 Aug 2026). The credit-integration tests below opt back in per-test
# via `settings.BILLING_CREDITS = True` and fund a balance explicitly.
pytestmark = [
    pytest.mark.django_db,
    pytest.mark.usefixtures("credits_disabled"),
]


@pytest.fixture
def credits_disabled(settings) -> None:
    settings.BILLING_CREDITS = False


def test_create_job_creates_a_queued_job_and_does_not_run_it_inline(
    django_capture_on_commit_callbacks,
) -> None:
    org = make_organization()
    user = make_user()
    with django_capture_on_commit_callbacks(execute=False):
        job = services.create_job(
            organization=org, actor=user, type=DEMO_JOB_TYPE, params={"items": [1, 2]}
        )
    assert job.status == Job.STATUS_QUEUED
    assert job.started_at is None
    assert Job.objects.filter(pk=job.pk).count() == 1


def test_replaying_the_same_idempotency_key_returns_the_original_job_and_creates_no_second_row(
    django_capture_on_commit_callbacks,
) -> None:
    org = make_organization()
    user = make_user()
    with django_capture_on_commit_callbacks(execute=False):
        first = services.create_job(
            organization=org,
            actor=user,
            type=DEMO_JOB_TYPE,
            params={"items": [1]},
            idempotency_key="key-1",
        )
        second = services.create_job(
            organization=org,
            actor=user,
            type=DEMO_JOB_TYPE,
            params={"items": [1, 2, 3]},  # different params — must still be ignored
            idempotency_key="key-1",
        )
    assert second.pk == first.pk
    assert Job.objects.filter(organization=org, idempotency_key="key-1").count() == 1


def test_replaying_the_same_idempotency_key_creates_no_second_credit_hold(
    settings, django_capture_on_commit_callbacks
) -> None:
    settings.BILLING_CREDITS = True
    org = make_organization()
    user = make_user()
    credits.grant(org, 100)

    with django_capture_on_commit_callbacks(execute=False):
        services.create_job(
            organization=org,
            actor=user,
            type=DEMO_JOB_TYPE,
            idempotency_key="key-2",
        )
        services.create_job(
            organization=org,
            actor=user,
            type=DEMO_JOB_TYPE,
            idempotency_key="key-2",
        )

    holds = CreditLedgerEntry.objects.filter(organization=org, kind=CreditLedgerEntry.KIND_HOLD)
    assert holds.count() == 1


def test_a_different_idempotency_key_creates_a_second_row(
    django_capture_on_commit_callbacks,
) -> None:
    org = make_organization()
    user = make_user()
    with django_capture_on_commit_callbacks(execute=False):
        first = services.create_job(
            organization=org, actor=user, type=DEMO_JOB_TYPE, idempotency_key="a"
        )
        second = services.create_job(
            organization=org, actor=user, type=DEMO_JOB_TYPE, idempotency_key="b"
        )
    assert first.pk != second.pk


def test_create_job_with_an_unknown_type_raises() -> None:
    org = make_organization()
    with pytest.raises(UnprocessableEntity):
        services.create_job(organization=org, actor=make_user(), type="nope.nope")


def test_create_job_places_a_credit_hold_when_credits_are_enabled(
    settings, django_capture_on_commit_callbacks
) -> None:
    settings.BILLING_CREDITS = True
    org = make_organization()
    credits.grant(org, 100)
    with django_capture_on_commit_callbacks(execute=False):
        job = services.create_job(organization=org, actor=make_user(), type=DEMO_JOB_TYPE)
    assert credits.get_balance(org) == 100 - 3  # demo job's credit_estimate
    assert CreditLedgerEntry.objects.filter(job=job, kind=CreditLedgerEntry.KIND_HOLD).exists()


def test_create_job_raises_payment_required_when_balance_is_insufficient(settings) -> None:
    settings.BILLING_CREDITS = True
    org = make_organization()
    with pytest.raises(PaymentRequired):
        services.create_job(organization=org, actor=make_user(), type=DEMO_JOB_TYPE)
    assert Job.objects.filter(organization=org).count() == 0


def test_cancel_job_marks_a_queued_job_failed_and_refunds_the_hold(settings) -> None:
    settings.BILLING_CREDITS = True
    org = make_organization()
    user = make_user()
    credits.grant(org, 100)
    job = Job.objects.create(organization=org, type=DEMO_JOB_TYPE, requested_by=user)
    credits.hold(org, 3, job=job, actor=user)

    cancelled = services.cancel_job(job=job, actor=user)

    assert cancelled.status == Job.STATUS_FAILED
    assert cancelled.error == "cancelled"
    assert credits.get_balance(org) == 100


def test_cancel_job_is_a_no_op_on_an_already_terminal_job() -> None:
    org = make_organization()
    user = make_user()
    job = Job.objects.create(
        organization=org, type=DEMO_JOB_TYPE, requested_by=user, status=Job.STATUS_SUCCEEDED
    )
    result = services.cancel_job(job=job, actor=user)
    assert result.status == Job.STATUS_SUCCEEDED


def test_the_database_constraint_rejects_a_duplicate_key_even_with_no_application_guard() -> None:
    """ddia#11: the ``UniqueConstraint`` itself, independent of
    ``create_job``'s own guards — proves the database, not just the
    service, refuses two rows for one (organization, idempotency_key)."""
    org = make_organization()
    Job.objects.create(
        organization=org, type=DEMO_JOB_TYPE, requested_by=make_user(), idempotency_key="dupe"
    )
    with pytest.raises(IntegrityError):
        Job.objects.create(
            organization=org, type=DEMO_JOB_TYPE, requested_by=make_user(), idempotency_key="dupe"
        )


def test_two_jobs_with_no_idempotency_key_do_not_collide() -> None:
    """The constraint's ``condition=~Q(idempotency_key="")`` — every job
    created without a key is exempt from the uniqueness it enforces on
    real keys."""
    org = make_organization()
    first = Job.objects.create(organization=org, type=DEMO_JOB_TYPE, requested_by=make_user())
    second = Job.objects.create(organization=org, type=DEMO_JOB_TYPE, requested_by=make_user())
    assert first.pk != second.pk


def test_create_job_survives_a_race_the_select_for_update_guard_misses(
    django_capture_on_commit_callbacks,
) -> None:
    """ddia#11: ``select_for_update`` inside ``create_job`` locks a row
    that doesn't exist yet when two requests both read ``None`` for the
    same key — it cannot stop both from proceeding to
    ``Job.objects.create``. This simulates exactly that race (patching the
    lookup to keep returning ``None`` even though a row already exists)
    and proves the database ``UniqueConstraint`` is the real backstop:
    the loser's ``IntegrityError`` is caught and it returns the winner's
    row instead of raising or creating a second one."""
    org = make_organization()
    user = make_user()

    with django_capture_on_commit_callbacks(execute=False):
        winner = services.create_job(
            organization=org, actor=user, type=DEMO_JOB_TYPE, idempotency_key="raced"
        )

        with patch("keel.jobs.services.Job.objects.select_for_update") as mock_select_for_update:
            mock_select_for_update.return_value.filter.return_value.first.return_value = None
            loser = services.create_job(
                organization=org, actor=user, type=DEMO_JOB_TYPE, idempotency_key="raced"
            )

    assert loser.pk == winner.pk
    assert Job.objects.filter(organization=org, idempotency_key="raced").count() == 1


def test_create_job_pins_step_count_from_the_registry_at_creation(
    django_capture_on_commit_callbacks,
) -> None:
    """ddia#24: ``Job.step_count`` is stamped once, at creation, from
    the registry's step list — the runner totals against this column,
    never a live re-read of the registry (see
    ``keel.jobs.runner.run_job``)."""
    org = make_organization()
    with django_capture_on_commit_callbacks(execute=False):
        job = services.create_job(organization=org, actor=make_user(), type=DEMO_JOB_TYPE)
    assert job.step_count == 3  # demo job's three steps


def test_create_job_stamps_a_params_version(django_capture_on_commit_callbacks) -> None:
    """ddia#24: every job's params carry a version tag so a resumed job
    (or a future migration of the params shape) can tell which shape it
    was written against."""
    org = make_organization()
    with django_capture_on_commit_callbacks(execute=False):
        job = services.create_job(
            organization=org, actor=make_user(), type=DEMO_JOB_TYPE, params={"items": [1]}
        )
    assert job.params["_v"] == services.PARAMS_VERSION
    assert job.params["items"] == [1]

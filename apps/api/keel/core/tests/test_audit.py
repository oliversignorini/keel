import pytest
from django.db import transaction

from keel.core.audit import AuditRecord, audited, not_audited, registry


def test_audited_registers_the_function_with_its_action() -> None:
    @audited("widget.create")
    def create_widget(*, actor=None):
        return "widget-1"

    entry = registry.get(create_widget)

    assert entry["kind"] == "audited"
    assert entry["action"] == "widget.create"


def test_not_audited_registers_the_function_with_its_reason() -> None:
    @not_audited("read-only, nothing to record")
    def list_widgets():
        return []

    entry = registry.get(list_widgets)

    assert entry["kind"] == "not_audited"
    assert entry["reason"] == "read-only, nothing to record"


def test_not_audited_does_not_change_call_behaviour() -> None:
    @not_audited("read-only")
    def add(a, b):
        return a + b

    assert add(2, 3) == 5


def test_registry_is_enumerable() -> None:
    @audited("fixture.enumerable_action")
    def fixture_audited_fn():
        return None

    @not_audited("fixture reason")
    def fixture_not_audited_fn():
        return None

    entries = dict(registry)

    assert any(k.endswith("fixture_audited_fn") for k in entries)
    assert any(k.endswith("fixture_not_audited_fn") for k in entries)
    assert len(registry) >= 2


@pytest.mark.django_db
def test_audited_returns_the_wrapped_functions_result() -> None:
    @audited("fixture.returns_result")
    def compute(*, actor=None):
        return 42

    assert compute(actor="someone") == 42


@pytest.mark.django_db(transaction=True)
def test_audited_records_with_actor_target_impersonator_metadata() -> None:
    recorded: list[AuditRecord] = []

    @audited("fixture.record_full")
    def do_the_thing(*, actor, impersonator=None, target=None, metadata=None):
        return "the-target"

    from keel.core import audit as audit_module

    audit_module.set_recorder(recorded.append)
    try:
        with transaction.atomic():
            do_the_thing(actor="user-1", impersonator="admin-1", metadata={"note": "test"})
    finally:
        audit_module.set_recorder(audit_module._default_recorder)

    assert len(recorded) == 1
    record = recorded[0]
    assert record.action == "fixture.record_full"
    assert record.actor == "user-1"
    assert record.impersonator == "admin-1"
    assert record.target == "the-target"
    assert record.metadata == {"note": "test"}


@pytest.mark.django_db(transaction=True)
def test_audited_records_inline_not_deferred_to_commit() -> None:
    """The recorder runs inline, inside the same transaction as
    the effect it records, rather than via ``transaction.on_commit()``.
    AuditLog lives in the same Postgres as everything it describes, so a
    dual write across a commit boundary buys nothing but a window where
    the effect is durable and the audit row is silently lost."""
    recorded: list[AuditRecord] = []

    @audited("fixture.recorded_inline")
    def do_the_thing(*, actor=None):
        return None

    from keel.core import audit as audit_module

    audit_module.set_recorder(recorded.append)
    try:
        with transaction.atomic():
            do_the_thing(actor="user-1")
            assert len(recorded) == 1  # recorded inline, before the transaction commits
    finally:
        audit_module.set_recorder(audit_module._default_recorder)

"""The job registry (PRD §5.5.1)."""

import pytest

from keel.jobs.registry import (
    DuplicateJobType,
    JobStepSpec,
    JobTypeRegistry,
    JobTypeSpec,
    StepContext,
    UnknownJobType,
)


def _spec(type_: str = "t.example") -> JobTypeSpec:
    return JobTypeSpec(
        type=type_,
        queue="default",
        credit_estimate=5,
        steps=(JobStepSpec(name="only", run=lambda ctx: "ok"),),
    )


def test_register_and_get_round_trips() -> None:
    registry = JobTypeRegistry()
    spec = _spec()
    registry.register(spec)
    assert registry.get("t.example") is spec
    assert "t.example" in registry
    assert len(registry) == 1
    assert list(registry) == [spec]


def test_get_unknown_type_raises() -> None:
    registry = JobTypeRegistry()
    with pytest.raises(UnknownJobType):
        registry.get("nope")


def test_registering_the_same_type_twice_raises() -> None:
    registry = JobTypeRegistry()
    registry.register(_spec())
    with pytest.raises(DuplicateJobType):
        registry.register(_spec())


def test_a_job_type_with_no_steps_is_rejected() -> None:
    registry = JobTypeRegistry()
    with pytest.raises(ValueError):
        registry.register(JobTypeSpec(type="empty", queue="default", credit_estimate=1, steps=()))


def test_step_names_reflects_declared_order() -> None:
    spec = JobTypeSpec(
        type="t.ordered",
        queue="default",
        credit_estimate=1,
        steps=(
            JobStepSpec(name="a", run=lambda ctx: None),
            JobStepSpec(name="b", run=lambda ctx: None),
        ),
    )
    assert spec.step_names() == ("a", "b")


def test_step_context_carries_prior_results() -> None:
    context = StepContext(job_id="1", organization_id="org", params={"x": 1}, results={"a": "1"})
    assert context.results["a"] == "1"
    assert context.params["x"] == 1

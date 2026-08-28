"""The job registry (PRD §5.5.1).

Each job type declares its steps, its queue, and its credit estimate.
This is the one part a project is expected to replace, so it stays
small and obvious: a couple of dataclasses and a dict, registered at
import time by each job type's own module (see ``keel/jobs/demo.py``
for the shape a project's own job types copy).

A step function receives a :class:`StepContext` and returns a small
JSON-serialisable value (or ``None``) that becomes ``JobStep.output_ref``
and is made available to every later step of the same job via
``StepContext.results`` — deliberately opaque past that; a step that
needs its predecessor's real output re-derives it or loads it from
wherever it actually lives (a file, a row), the same way a resumed job
would.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StepContext:
    job_id: Any
    organization_id: Any
    params: dict[str, Any]
    results: dict[str, Any]


StepFunc = Callable[[StepContext], Any]


@dataclass(frozen=True)
class JobStepSpec:
    name: str
    run: StepFunc


@dataclass(frozen=True)
class JobTypeSpec:
    type: str
    queue: str
    credit_estimate: int
    steps: tuple[JobStepSpec, ...]

    def step_names(self) -> tuple[str, ...]:
        return tuple(step.name for step in self.steps)


class UnknownJobType(Exception):
    def __init__(self, type_: str) -> None:
        self.type = type_
        super().__init__(f"No job type registered for {type_!r}.")


class DuplicateJobType(Exception):
    def __init__(self, type_: str) -> None:
        self.type = type_
        super().__init__(f"Job type {type_!r} is already registered.")


class JobTypeRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, JobTypeSpec] = {}

    def register(self, spec: JobTypeSpec) -> JobTypeSpec:
        if not spec.steps:
            raise ValueError(f"job type {spec.type!r} must declare at least one step")
        if spec.type in self._specs:
            raise DuplicateJobType(spec.type)
        self._specs[spec.type] = spec
        return spec

    def get(self, type_: str) -> JobTypeSpec:
        try:
            return self._specs[type_]
        except KeyError:
            raise UnknownJobType(type_) from None

    def __contains__(self, type_: str) -> bool:
        return type_ in self._specs

    def __iter__(self) -> Iterator[JobTypeSpec]:
        return iter(self._specs.values())

    def __len__(self) -> int:
        return len(self._specs)


registry = JobTypeRegistry()

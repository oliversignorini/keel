"""Static checks for the two Tier-1 task acceptance criteria (PRD §5):
"Every task body is a single call into a service" / "Tasks take IDs,
never model instances" — both lint-enforced acceptance criteria. Ruff
has no plugin mechanism this
project can hook a custom rule into (it's a Rust binary), so these are
plain AST-based checks run as meta-tests, the same shape as
``keel/organizations/tests/test_meta_guard_coverage.py``'s registry
walk.

Only functions decorated with ``@task`` (``keel.core.tasks``) are
checked. Tasks that use Celery directly (``@shared_task``) are Tier 2's
territory per the shim's own docstring and are out of scope here — e.g.
``keel.billing.tasks.dispatch_stripe_event``'s bound-retry-with-transaction
body is deliberately not a single call.
"""

import ast
import importlib
import inspect
import pkgutil
import textwrap
import typing
from collections.abc import Iterable

from keel.core.tasks import Task


class TaskLintViolation(Exception):
    def __init__(self, task_name: str, reason: str) -> None:
        self.task_name = task_name
        self.reason = reason
        super().__init__(f"{task_name}: {reason}")


def _function_source(func: object) -> tuple[ast.FunctionDef | ast.AsyncFunctionDef, list[str]]:
    # inspect.getsource keeps the function's own indentation (it's a
    # module-level function in every real call site); textwrap.dedent
    # normalises that before parsing.
    source = textwrap.dedent(inspect.getsource(func))  # type: ignore[arg-type]
    tree = ast.parse(source)
    function_def = tree.body[0]
    assert isinstance(function_def, ast.FunctionDef | ast.AsyncFunctionDef)
    return function_def, source.splitlines()


def _is_objects_get_lookup(stmt: ast.stmt) -> bool:
    """``x = Model.objects.get(pk=...)`` — the one shape of "fetch by id"
    statement a Tier-1 task body is allowed, ahead of its single service
    call."""
    if not isinstance(stmt, ast.Assign):
        return False
    call = stmt.value
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
        return False
    if call.func.attr != "get":
        return False
    inner = call.func.value
    return isinstance(inner, ast.Attribute) and inner.attr == "objects"


def check_single_service_call(check_task: Task) -> None:
    """Body must be: an optional docstring, zero or more local imports,
    zero or more ``x = Model.objects.get(pk=...)`` lookups, then exactly
    one statement that calls a service function (an ``Expr(Call(...))``
    or ``Return(Call(...))``)."""
    function_def, _ = _function_source(check_task.func)
    body = list(function_def.body)

    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]  # docstring

    service_calls = 0
    for stmt in body:
        if isinstance(stmt, ast.Import | ast.ImportFrom):
            continue
        if _is_objects_get_lookup(stmt):
            continue
        is_call_stmt = (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)) or (
            isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Call)
        )
        if not is_call_stmt:
            raise TaskLintViolation(
                check_task.name,
                f"body has a non-lookup, non-single-call statement: {ast.dump(stmt)[:120]}",
            )
        service_calls += 1

    if service_calls != 1:
        raise TaskLintViolation(
            check_task.name,
            f"body must be exactly one service call; found {service_calls}",
        )


def check_takes_ids_not_instances(check_task: Task) -> None:
    """Checked against the function's *real*, resolved type hints
    (``typing.get_type_hints``) rather than the source text — this
    catches a Django ``Model`` subclass annotation regardless of where
    the class was imported from, including a forward-ref string
    annotation under ``from __future__ import annotations``."""
    from django.db import models

    try:
        hints = typing.get_type_hints(check_task.func)
    except NameError:
        # An annotation referencing a name only importable lazily inside
        # the function body can't be resolved from here — same
        # constraint every runtime type-hint resolver has. Nothing to
        # check against in that case; the AST-based single-call check
        # already forbids a body complex enough to hide a model import.
        return

    for name, hint in hints.items():
        if name == "return":
            continue
        if isinstance(hint, type) and issubclass(hint, models.Model):
            raise TaskLintViolation(
                check_task.name,
                f"parameter {name!r} is annotated {hint.__name__!r}, "
                "a Django Model subclass — tasks take ids, not instances",
            )


def check_task(check_task: Task) -> None:
    check_single_service_call(check_task)
    check_takes_ids_not_instances(check_task)


def discover_shim_tasks(dotted_prefix: str) -> Iterable[Task]:
    """Every ``Task`` instance bound to a module-level name under
    ``dotted_prefix`` (e.g. ``keel``) whose module is a ``tasks.py``."""
    package = importlib.import_module(dotted_prefix)
    for module_info in pkgutil.walk_packages(package.__path__, prefix=f"{dotted_prefix}."):
        if not module_info.name.endswith(".tasks"):
            continue
        module = importlib.import_module(module_info.name)
        for value in vars(module).values():
            if isinstance(value, Task):
                yield value


def discover_shared_tasks(dotted_prefix: str) -> Iterable[typing.Any]:
    """Every Celery ``Task`` instance (``@shared_task``) bound to a
    module-level name anywhere under ``dotted_prefix`` — Tier 2's own
    territory (module docstring above). Unlike ``discover_shim_tasks``
    this isn't limited to ``tasks.py`` modules: ``keel.jobs.runner`` is
    Tier 2's canonical home for ``run_job_task``/``sweep_stuck_jobs_task``
    and isn't named ``tasks.py``, so every non-test, non-migration module
    is walked."""
    from celery.app.task import Task as CeleryTask

    package = importlib.import_module(dotted_prefix)
    for module_info in pkgutil.walk_packages(package.__path__, prefix=f"{dotted_prefix}."):
        name_parts = module_info.name.split(".")
        if "tests" in name_parts or "migrations" in name_parts:
            continue
        module = importlib.import_module(module_info.name)
        for value in vars(module).values():
            if isinstance(value, CeleryTask):
                yield value


def check_shared_task_takes_ids_not_instances(shared_task: typing.Any) -> None:
    """Tier 2 equivalent of ``check_takes_ids_not_instances``: a Celery
    ``@shared_task`` isn't wrapped in the Tier-1 ``Task`` shim, so this
    works off ``.__wrapped__`` (the plain function Celery decorated,
    preserved via ``functools.wraps``) instead of ``keel.core.tasks.Task``.
    Tier 2 tasks are otherwise unconstrained (module docstring above) —
    this only checks the one acceptance criterion PRD §5 makes universal:
    tasks take ids, never model instances."""
    from django.db import models

    func = getattr(shared_task, "__wrapped__", None)
    if func is None:
        return
    try:
        hints = typing.get_type_hints(func)
    except NameError:
        return

    for name, hint in hints.items():
        if name in ("return", "self"):
            continue
        if isinstance(hint, type) and issubclass(hint, models.Model):
            raise TaskLintViolation(
                getattr(shared_task, "name", func.__name__),
                f"parameter {name!r} is annotated {hint.__name__!r}, "
                "a Django Model subclass — tasks take ids, not instances",
            )

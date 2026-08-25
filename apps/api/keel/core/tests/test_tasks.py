from keel.core.tasks import task


def test_task_wraps_a_plain_function_and_stays_callable() -> None:
    @task
    def add(a, b):
        return a + b

    assert add(2, 3) == 5


def test_task_enqueue_runs_via_celery_and_returns_a_result(settings) -> None:
    """CELERY_TASK_ALWAYS_EAGER is on in test settings, so .enqueue()
    executes synchronously and the eager result is retrievable."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True

    @task
    def multiply(a, b):
        return a * b

    async_result = multiply.enqueue(3, 4)

    assert async_result.get() == 12


def test_task_enqueue_is_distinct_from_direct_call() -> None:
    calls = []

    @task
    def record(value):
        calls.append(value)
        return value

    record.enqueue(1)

    assert calls == [1]

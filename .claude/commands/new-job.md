Generate a job type for `$ARGUMENTS` — a name and, if given, a rough step
list. First decide the tier (CLAUDE.md invariant 5) — the CLI will not
guess this for you, `--tier` is required:

- **Tier 1** (single step, fire-and-forget, succeeds or retries — an
  email, a sync, a rollup): this is not a job, it's a task.
- **Tier 2** (multi-step, resumable, streams progress, can partially
  succeed): use `keel/jobs/`.

**Ask** if it isn't clear which tier fits — extending Tier 1 to cover
Tier-2 work is the specific mistake `keel/core/tasks.py`'s docstring warns
against, and the generator enforces the split by requiring the flag
rather than inferring it.

## 1. Run the generator

**Tier 1** — appends one `@task`-decorated function to an existing app's
`tasks.py`, delegating to a `services.py` function of the same name:

```
pnpm gen job __Name__ --tier 1 --app <app>
```

`<app>` must already exist and its `tasks.py` must already
`from keel.<app> import services` (true of anything `/new-resource`
generated). The generator refuses to run if the function name is already
taken — pick a different job name or remove the existing one by hand.

**Tier 2** — emits `keel/jobs/<name>.py` (steps, `JobTypeSpec`
registration) plus tests, following `keel/jobs/demo.py`'s shape, and
splices the registration into `JobsConfig.ready()`:

```
pnpm gen job __Name__ --tier 2 --steps "fetch,transform,publish"
```

`--steps` is optional (defaults to one `run` step) and deliberately
minimal — every generated step is a stub returning `None`; the tests
prove each step is callable, that a job resumes after a simulated worker
kill without re-running a completed step, and that running the same job
twice doesn't fork its step set. Both tiers run the DB-free gates
(`makemigrations --check`, `lint-imports`, `check_permission_lint.py`)
and print exactly which files were written and which anchor was spliced.

## 2. Do the judgement work

- **Tier 1:** implement the `services.<name>` function the task delegates
  to; give the task the parameters it actually needs and pass them
  through at its `.enqueue(...)` call site — the generator's one-line
  delegation has none, since the parameters are the whole judgement call.
- **Tier 2:** fill in each step's real work in `keel/jobs/<name>.py`. Wire
  creation through `keel/jobs/services.py`'s job-creation service — don't
  hand-roll `Job`/`JobStep` row creation. If the job needs per-tenant
  concurrency limits, use `keel/jobs/concurrency.py`'s existing primitive.
  If progress needs to reach the browser live, use `keel/jobs/sse.py` /
  `keel/jobs/pubsub.py` — don't add polling. Neither is wired by the
  generator.

## 3. Permissions

Jobs of a new domain need view/create codes the same way a resource does
— see `Perm.JOBS_VIEW` / `Perm.JOBS_CREATE` for the existing pattern, or
run `/new-permission` for codes scoped to this job type if it needs finer
control than "can create any job".

## Finish

`/check-invariants` — job code is regular service code for invariant 7
(audit) purposes if it writes anything outside the job/step rows
themselves.

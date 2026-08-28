Add a transactional email named in `$ARGUMENTS` (e.g. `invoice-overdue`).
Follow `keel/notifications/emails.py`'s existing six emails exactly —
this is a two-sided change, template plus sender, and both sides use the
existing build pipeline. Do not invent a runtime-rendering path.

1. **Template** — `packages/emails/templates/<name>.tsx`, a react-email
   component matching the existing templates' use of `Layout.tsx` and
   `{{TOKEN}}`-style placeholders for values substituted at send time
   (see `verification.tsx` for the shape).
2. **Sender** — in `keel/notifications/emails.py`, add
   `send_<name>_email(*, to: str, ...tokens) -> None` calling the private
   `_send(to=..., subject=..., template_name="<name>", tokens={...})`
   helper every other sender uses. Do not call `_render` or
   `EmailMultiAlternatives` directly — `_send` is the one path.
3. **Call site** — dispatch it from the owning service via a Tier-1 task
   (`keel.core.tasks`), same as `keel/widgets/tasks.py`'s
   `notify_widget_created_task` pattern (or `docs/reference-slice/api-widgets/tasks.py`
   if the demo slice was moved there, or any other app's `tasks.py` if it
   was deleted — the pattern is one line: the service does the write and
   schedules the task on `transaction.on_commit()`; the task calls the
   sender). Never call a sender function directly from inside an open
   transaction.
4. Route the task through the `email` queue, not `default`.

## Local verification

`packages/emails/dist/<name>.html` doesn't exist until built — Django
raises `EmailTemplateMissing` if you try to send before building:

```
pnpm --filter @keel/emails build
```

CI's `test-api` job runs this before pytest; if you skip it locally,
every test that sends this email will fail with the same error CI would
catch.

## Tests

- A rendering test that the built HTML contains the substituted token
  values, not the literal `{{TOKEN}}` placeholders.
- A test on the call site that the task is enqueued via
  `transaction.on_commit()`, not synchronously inside the service.

## Finish

`/check-invariants` if the sender's call site is a new or changed
service function (audit coverage, invariant 7).

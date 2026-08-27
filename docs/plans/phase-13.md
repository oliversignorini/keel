# Phase 13 — Document storage foundation

**Source of truth:** Notion "Keel Phase 13", the direction proposal's §3.
**Depends on:** Phase 10 merged.
**Size:** Medium.
**Parallel with:** Phases 14 and 15 — different apps, no shared files.

---

## What already exists — do not rebuild

`keel/files/` is real: a model, `services.py`, an S3/R2 client
(`r2_client.py`), presigned upload-create / upload-complete / detail views,
`moto`-mocked tests, and MinIO in `infra/compose.dev.yml` for local dev.
The Notion checklist's "design generic Document/File metadata model" is
already answered.

The gaps are narrower and more specific:

- The model is 29 lines. No checksum, no explicit status lifecycle, no soft
  delete.
- `r2_client.py` is a concrete client, not a **storage adapter**. The
  direction proposal asks for a seam so provider choice stays flexible.
  Django 5+ ships `STORAGES`; prefer that over inventing an abstraction.
- No list and no delete. Upload and retrieve only.
- Nothing documents what happens to orphaned objects when a row is deleted,
  or to orphaned rows when an upload never completes.

## Boundary

**In scope:** `keel/files/`, its tests, storage settings, storage docs.

**Out of scope:**

| Thing | Owner |
|---|---|
| Anything AI, extraction, parsing, OCR, embeddings, or document *understanding* | Brein. Not Keel. This is the boundary the whole project rests on |
| Virus scanning, thumbnailing, preview generation | Out — name them as extension points instead |
| `keel/billing`, `keel/jobs`, `keel/audit` | Phases 14 and 15, running concurrently |

**One migration is allowed here** — it is the first legitimate exception to
the baseline-migration invariant since Phase 1, and it must be a single
migration covering every field this phase adds. Say so in the report.

## Work

- Extend the model: checksum (sha256 of the uploaded bytes, verified on
  complete), MIME type, size, storage key, an explicit status lifecycle
  (`pending` → `available`, plus a terminal failure state), timestamps, and
  the workspace relation it already has. Enforce size and content-type
  limits at the service layer, configurably.
- Introduce the storage seam via Django's `STORAGES` setting. Local
  filesystem for dev without MinIO, MinIO for dev with it, S3-compatible for
  production. One settings change to switch; no code change.
- Complete the CRUD: list (cursor-paginated, tenant-scoped) and delete
  (decide and document soft vs hard, and what happens to the object).
- Permission checks on every operation, registered in
  `organizations/permissions.py` like everything else — `files.view`,
  `files.upload`, `files.delete` or whatever the naming convention there
  dictates. Each guard needs an allow test and a deny test asserting the
  **reason**, or the meta-test fails you.
- A garbage-collection path for uploads that never complete. A periodic
  Celery task is fine; leaving them forever is not.
- `docs/storage.md`: the adapter seam, provider options (S3, R2, Supabase
  Storage), what Railway volumes are and are not good for, and the
  production caveats.

## Acceptance — evidence required

- [ ] Upload → complete → list → retrieve → delete, each tenant-scoped and permission-checked, each tested
- [ ] Cross-organisation access to a file answers **404** — covered by the tenant-isolation meta-test, not a hand-written test
- [ ] Checksum verified on completion; a corrupted upload is rejected, tested
- [ ] Size and content-type limits enforced at the service layer, tested
- [ ] Switching storage backend is a settings change only — demonstrated across local and MinIO
- [ ] Incomplete uploads are collected; the task is tested
- [ ] Every mutating service is `@audited` or `@not_audited(reason=…)`
- [ ] Exactly one migration
- [ ] `docs/storage.md` written; no AI or extraction functionality anywhere in the diff

## Report back

What you extended vs rebuilt; the delete semantics you chose and why; the
extension points Brein will need and where they hook in.

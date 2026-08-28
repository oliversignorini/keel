# File storage

Covers the upload lifecycle, the storage adapter seam, provider options,
and the
production caveats — including why Railway's persistent volumes are not
the answer, a question this template will otherwise get asked often
given it deploys to Railway by default (`docs/deploy-railway.md`).

## What this is not

`keel/files/` handles _storage_: presigned direct upload, a status
lifecycle, listing, retrieval and (soft) deletion, tenant isolation,
garbage collection. It does not — and, by this project's own stated
boundary, never will — do anything with the
_contents_ of a file: no OCR, no text extraction, no embeddings, no
document understanding. That's a different project's problem (Brein);
this template only guarantees the bytes exist, belong to the right
organisation, and are named honestly (`content_type`, `size`, checksum)
by the time a caller downstream tries to do something with them. Virus
scanning, thumbnailing and preview generation are the same story — named
here as extension points (see "Extension points" below), not built.

## The upload lifecycle

```
pending ──────► available   (checksum verified, size/content_type/etag
  │                           taken from the storage provider's own
  │                           HeadObject — never the client)
  │
  ├──────────► failed        (checksum mismatch, or the object that
  │                           actually landed violates the configured
  │                           size/content-type policy)
  │
  └──────────► expired       (keel.files.tasks.sweep_stale_uploads:
                              nobody ever called complete)

{available, failed} ──────► deleted   (a tombstone — see below)
```

Every arrow is a guarded `UPDATE ... WHERE status = <expected>`
(`keel/files/services.py`), not an unconditional assignment — two
concurrent completions of the same upload both pass the existence check,
but only one moves the row out of `pending`; the other's update matches
zero rows and is treated as "someone already decided this", not an
error. The same pattern covers delete.

**Why five states, not two.** An earlier model shipped `pending` /
`complete` only — no way to represent a corrupted upload, an abandoned
one, or a deleted one. Retrofitting states onto a machine that already
has rows in it is real migration work, so this is where that gets
designed in rather than deferred again.

**Checksum verification.** The client declares a `checksum_sha256` at
create time — what it's about to upload. On completion, the server
downloads the object back and hashes it (`ObjectStorage.compute_sha256`),
comparing against the declaration; a mismatch fails the row rather than
letting it reach `available`. This costs a second transfer server-side.
The alternative — S3's native checksum-algorithm PUT header, verified by
the provider itself — would avoid that, but this template's own test
double (moto) doesn't independently verify a client-supplied
`x-amz-checksum-sha256` header against the bytes actually sent, so a
test asserting rejection would only prove moto trusts the client, not
that corruption is caught. Real S3 does verify it; a project confident
its production provider does too can move this check to PUT time as a
follow-up — see "Extension points" below. For the document sizes this
template targets, the extra transfer is the right trade today.

**Size and content type.** `FILES_MAX_UPLOAD_SIZE_BYTES` and
`FILES_ALLOWED_CONTENT_TYPES` (`config/settings/base.py`) are enforced
twice: against the client's declared values at create time (reject
obviously-bad requests early) and again against the storage provider's
observed `HeadObject` values at completion (a client can't declare a
small size to pass the first check and then upload something larger —
ddia review finding 21).

**Deletion is a tombstone, not a row delete.** `services.delete_file`
moves an `available`/`failed` row to `deleted` and stamps `deleted_at`;
the row stays. The actual storage object is removed out-of-band: a
Tier-1 fire-and-forget task (`keel.core.tasks`) dispatched on commit,
backstopped by `keel.files.tasks.sweep_stale_uploads` retrying any row
whose `object_purged` flag never flipped (the same gap
`keel.billing.tasks.sweep_unprocessed_stripe_events` covers for
webhooks — a dispatch that never reached the broker at all). Deleting the
row outright was rejected for two reasons: it leaves nothing to know an
object needs cleaning up if the delete request dies mid-flight, and it
would force the delete call to make a synchronous storage round trip
inside the request. A soft-deleted row drops out of `list_files` but its
detail route still answers — deletion here means "gone", not "never
existed".

**Garbage collection.** `keel.files.tasks.sweep_stale_uploads` runs
every 15 minutes (`CELERY_BEAT_SCHEDULE`) and does two things: expires
`pending` rows older than `FILES_PENDING_UPLOAD_TTL_SECONDS` (default 24
hours — an abandoned upload that never got a completion call), and
retries the tombstone-purge for `deleted` rows that haven't confirmed
their object gone yet. Both halves are idempotent run twice, the same
discipline every scheduled job in this codebase is held to
(`keel/files/tests/test_sweep.py`).

**Why `organization` is `PROTECT`, not `CASCADE`.** Every other
`OrgScopedModel` inherits `CASCADE` from `keel.core.models` — right for
pure metadata rows. `FileUpload` overrides it: a hard-deleted
`Organization` row must never silently drop upload rows and orphan their
storage objects with no tombstone left to drive cleanup from. This
app's own delete path never triggers it (organisation deletion in this
codebase is itself a soft delete —
`organizations.services.delete_organization`), but `PROTECT` means any
future hard-delete path (an admin action, a GDPR-erasure command) is
forced to decide what happens to an organisation's files on purpose,
rather than finding out from an orphaned bucket months later.

## The storage adapter seam

`keel/files/storage.py` defines `ObjectStorage`, a small protocol
(`generate_presigned_upload`, `generate_presigned_download`,
`head_object`, `compute_sha256`, `delete_object`, `ensure_ready`) that
`services.py` and `views.py` call through exclusively — neither imports
boto3 or a filesystem path directly. Which implementation is active is
Django's own `STORAGES` setting (`config/settings/base.py`):

```python
STORAGES = {
    "default": {...},       # Django's own default — unused by this app
    "staticfiles": {...},
    "files": {
        "BACKEND": KEEL_FILES_STORAGE_BACKEND,   # <- the switch
        "OPTIONS": {
            "endpoint_url": R2_ENDPOINT_URL,
            "access_key_id": R2_ACCESS_KEY_ID,
            "secret_access_key": R2_SECRET_ACCESS_KEY,
            "bucket": R2_BUCKET,
        },
    },
}
```

Two implementations ship:

- **`keel.files.storage.S3CompatibleStorage`** — boto3 against any
  S3-compatible endpoint. This is the default, and covers MinIO (dev),
  R2 (production), and moto (tests) unchanged — all three speak the same
  API, so only `OPTIONS` (sourced from the `R2_*` env vars) differs
  between them.
- **`keel.files.storage.LocalFileSystemStorage`** — plain disk under
  `MEDIA_ROOT/files`, for a developer who doesn't want to run the MinIO
  container. There is no S3-shaped "presign a PUT" primitive for a local
  disk, so its upload/download URLs are ordinary, session-authenticated
  app routes (`PUT`/`GET .../files/{id}/local-object/`) rather than
  bucket URLs — see that class's docstring. `LocalFileSystemStorage`'s
  constructor accepts and ignores the S3-shaped `OPTIONS` keys
  (`endpoint_url`, `access_key_id`, ...), which is what makes flipping
  `KEEL_FILES_STORAGE_BACKEND` alone — no `OPTIONS` edit — enough to
  switch.

**Switching backends is a settings change only.**
`keel/files/tests/test_local_storage.py` runs the same upload -> complete
-> download -> delete flow `test_uploads.py` runs against moto, instead
against `LocalFileSystemStorage`, with nothing touched but
`STORAGES["files"]["BACKEND"]` — the acceptance criterion this doc
names, demonstrated as a test rather than asserted in prose.

```bash
# Local disk, no MinIO container required:
KEEL_FILES_STORAGE_BACKEND=keel.files.storage.LocalFileSystemStorage

# MinIO / R2 / real S3 (the default):
KEEL_FILES_STORAGE_BACKEND=keel.files.storage.S3CompatibleStorage
```

## Provider options

| Provider             | Backend                  | Notes                                                                                                                                                                                                                                                                                                                                     |
| -------------------- | ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Local disk**       | `LocalFileSystemStorage` | Solo dev only. Single-process, no presigned bucket URLs, not multi-instance-safe. Never use in production.                                                                                                                                                                                                                                |
| **MinIO**            | `S3CompatibleStorage`    | Dev/CI parity with a real S3-shaped API — `infra/compose.dev.yml`'s `minio` service. Real presigned-URL behaviour without a cloud account.                                                                                                                                                                                                |
| **Cloudflare R2**    | `S3CompatibleStorage`    | This template's production default (PRD §5). S3-API-compatible, no egress fees, works unchanged with the same adapter used for MinIO.                                                                                                                                                                                                     |
| **AWS S3**           | `S3CompatibleStorage`    | Drop-in — set `R2_ENDPOINT_URL` to AWS's regional endpoint (or omit it for the default endpoint resolution) and the real credentials. Nothing else changes.                                                                                                                                                                               |
| **Supabase Storage** | `S3CompatibleStorage`    | Supabase Storage exposes an S3-compatible API (a separate endpoint and its own access-key pair from a project's Postgres credentials) — set `R2_ENDPOINT_URL` to the project's S3 endpoint. Not verified against a live Supabase project; the adapter makes no R2-specific assumption, but treat this row as "should work," not "tested." |

Anything else genuinely S3-compatible works the same way — the seam's
entire point is that a new provider is an `OPTIONS` change, never a code
change.

## What Railway volumes are — and are not — good for

Railway offers persistent volumes: durable disk attached to a service.
They are real and useful for some things (a self-hosted Postgres data
directory, a local cache) — but they are the wrong tool for this app's
file storage, for reasons worth being explicit about since "just mount a
volume" is the obvious-looking shortcut:

- **A volume is attached to one service instance, not shared across
  replicas.** The moment this API runs more than one instance (which
  Railway's own autoscaling can do), a file uploaded through instance A
  and later requested through instance B simply isn't there. Object
  storage (R2/S3/MinIO) has no such boundary — every instance talks to
  the same bucket over the network.
- **Presigned direct upload doesn't work against a volume at all.** The
  entire point of this app's upload flow (PRD §5) is that the browser
  PUTs bytes straight to the storage provider, never through Django. A
  volume has no HTTP surface of its own to presign a URL against —
  making it work would mean routing every upload's bytes through the
  Django process, which is both slower and a memory/bandwidth cost this
  design deliberately avoids.
- **Volumes don't survive every kind of deploy the same way object
  storage does.** Object storage is external to the compute layer by
  construction; a volume's lifecycle is coupled to the service it's
  attached to.

`LocalFileSystemStorage` exists for the _developer's own laptop_, not
for a Railway deployment — see the provider table above. Production
always means `S3CompatibleStorage` against R2, S3, or an equivalent.

## Extension points

Named here deliberately, because a project instantiating this template
will want at least one of them and the seam should make it a subclass,
not a rewrite:

- **Virus scanning.** A natural hook is between `complete_upload`'s
  checksum verification and the guarded transition to `available` — a
  project could add a `scanning` state between them, call an external
  scanner, and only reach `available` on a clean result. `failed`
  already exists as the rejection path.
- **Thumbnailing / preview generation.** Fits as a Tier-1 task
  (`keel.core.tasks`) dispatched from the same `transaction.on_commit()`
  hook `services.delete_file` already uses for object-purge — enqueue on
  the transition to `available` instead.
- **A trustworthy provider-native checksum.** If a project's production
  provider is confirmed to enforce `x-amz-checksum-sha256` at PUT time
  (real S3 does; verify for R2/MinIO/Supabase Storage's specific
  version), `complete_upload`'s `compute_sha256` round trip can be
  replaced with reading the provider's own reported checksum via
  `HeadObject(ChecksumMode="ENABLED")` — no second transfer.
- **A different provider entirely.** Implement `ObjectStorage`
  (`keel/files/storage.py`) — six methods — and point
  `KEEL_FILES_STORAGE_BACKEND` at it. No other file in this app changes.

## Permissions

`files.view` gates list/retrieve/download-URL; `files.manage` gates
create/complete/delete — the same two-code split `widgets` uses, chosen
over inventing `files.upload`/`files.delete` because delete is exactly
the kind of destructive-but-still-managing-the-resource action the
existing `*.manage` convention already covers everywhere else in this
codebase, and a third code here would be the only resource in the
project not to follow that pattern. Every route calls
`resolve_and_authorize`, and `FileUploadResource` is walked by the
tenant-isolation meta-test (PRD §4 invariant 7) — a cross-organisation
lookup 404s, never 403s.

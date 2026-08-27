Regenerate the TypeScript API client from the current Django + allauth
OpenAPI specs, and confirm it matches what CI will produce. Run this any
time a viewset, serializer, or URL changed.

**Before running:** confirm no other worktree is regenerating
`openapi.merged.json` or `packages/api-client/src/generated` right now —
only one may at a time (`docs/review-2026-08.md`); a collision here is an
unresolvable merge conflict, not a bug to fix.

1. Merge the specs:

   ```
   cd apps/api && uv run python ../../scripts/merge_openapi.py
   ```

   This regenerates `openapi.merged.json` at the repo root from
   drf-spectacular's DRF spec and allauth headless's `/_allauth/openapi.json`.

2. Generate the client:

   ```
   cd packages/api-client && pnpm generate
   ```

   Runs orval against `openapi.merged.json`, writing
   `packages/api-client/src/generated`. **Never hand-edit anything under
   `generated/`** — if the output looks wrong, the fix is in the Django
   view/serializer or in `orval.config.ts`, not in the generated file.

3. Confirm nothing is stale:

   ```
   git diff --exit-code -- openapi.merged.json packages/api-client/src/generated
   ```

   A clean diff means the client was already in sync. A diff means
   commit it — this is exactly what CI's `api-client-generation` and
   `contracts` jobs check, and a PR with drift here fails both.

4. Typecheck the result:

   ```
   pnpm --filter @keel/api-client typecheck
   ```

5. If `apps/web` consumes the changed endpoint, update its call sites and
   run `pnpm --filter web typecheck` to catch anything the new types
   broke.

Report which files changed (new endpoints, changed shapes, or none) —
don't just say "regenerated."

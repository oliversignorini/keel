# Removing the marketing site

PRD §8: `init` asks whether the project wants a public marketing site.
On "no", it must delete everything below — nothing else in the repo
depends on it.

## Routes

- `apps/web/app/(marketing)/` — the whole route group: `/`, `/pricing`,
  `/blog`, `/blog/[slug]`, `/legal/terms`, `/legal/privacy`, and their
  `opengraph-image.tsx` files.
- `apps/web/app/sitemap.ts`
- `apps/web/app/robots.ts`

## Content and config

- `apps/web/content/` — the MDX blog posts.
- `apps/web/content-collections.ts`
- `apps/web/lib/blog/` (`post-schema.ts` and its test).
- `apps/web/lib/site.ts` and `apps/web/lib/site.test.ts` — only used by the
  routes above.
- `apps/web/components/json-ld.tsx`
- `apps/web/lib/billing/feature-labels.ts` and its test — **check first**:
  this also fixes the pricing page's raw-entitlement-code display. If the
  pricing page moves into the app shell instead of being deleted outright,
  keep this pair and update its import.
- `.content-collections/` (generated output; already gitignored).

## Dependencies

Remove from `apps/web/package.json`:

- `@content-collections/cli`
- `@content-collections/core`
- `@content-collections/mdx`
- `@content-collections/next`

And its wiring:

- `withContentCollections(...)` wrapper in `apps/web/next.config.ts` —
  revert to a plain `NextConfig` export.
- The `"content-collections"` entry in `apps/web/tsconfig.json`'s `paths`
  and in `apps/web/vitest.config.ts`'s `resolve.alias`.
- The `content:build` script in `apps/web/package.json`, and its
  `pnpm run content:build &&` prefix on `typecheck`.

## Environment

- `NEXT_PUBLIC_SITE_URL` in `.env.example` — only `lib/site.ts` reads it.

## Tests

- `apps/web/e2e/marketing.spec.ts` — the marketing-only Playwright specs,
  kept in their own file for exactly this deletion.

## What must NOT move with it

`apps/web/lib/auth/route-guard.ts` and `apps/web/middleware.ts` never
special-case the marketing routes — they are already outside the
middleware's `matcher`. Deleting the route group needs no middleware
change.

# Local dev: reaching the app

The app shell lives on its own subdomain, split from marketing and auth
on the apex. Locally that means:

```
app.lvh.me:3000    -> Next.js, the (app) route group   (the product itself)
lvh.me:3000        -> Next.js, the (marketing) route group + (auth)
api.lvh.me:8000    -> Django
```

Copy `.env.example` to `.env` at the repo root, and copy the
`NEXT_PUBLIC_*` lines out of it into `apps/web/.env.local`:

```bash
cp .env.example .env
grep '^NEXT_PUBLIC' .env.example > apps/web/.env.local
```

Django reads `apps/api/.env` first and falls back to the repo-root `.env`,
so either location works; the root is the one `.env.example` sits next to.
Then run `pnpm dev` as usual — nothing else changes about the dev workflow.

## Why `lvh.me`, not `app.localhost`

The session cookie has to be shared between the web origin and the API
origin (`Domain=.lvh.me`, PRD §4 "Auth architecture"). Browsers
special-case `localhost` and handle a `Domain=.localhost` cookie
attribute inconsistently, so `app.localhost` talking to `api.localhost`
would likely authenticate in production while silently failing to
authenticate in dev — the worst failure shape, because it only shows up
on the machine you'd least expect it on.

`lvh.me` is a public DNS name whose wildcard resolves to `127.0.0.1` —
`app.lvh.me` and `api.lvh.me` both resolve to `127.0.0.1`. No
`/etc/hosts` edit needed.

**The one real weakness:** `lvh.me` is a third-party DNS record, so this
setup does not work offline. If you need it to, add to your hosts file:

```
127.0.0.1 keel.test app.keel.test api.keel.test
```

and swap every `*.lvh.me` in `.env` for the matching `*.keel.test` host.

## Logging in during dev

Sign up / log in on `lvh.me:3000` (the apex — that's where `(auth)`
lives). A successful login lands you on `app.lvh.me:3000`. Visiting the
app host while signed out redirects you back to the apex login with a
`next=` that returns you to the app host afterward — this is the
behaviour `apps/web/e2e/cross-host-login.spec.ts` drives in a real
browser (see `apps/web/playwright.cross-host.config.ts` for how to run
it — it has no `webServer` of its own; it drives whatever `pnpm dev` /
`manage.py runserver` already have running on the `lvh.me` topology).

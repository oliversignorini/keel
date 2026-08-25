# Deploying Keel to Railway

This is a stub. Phase 0 only resolves the one question the PRD calls out as
needing an answer before Phase 5.5 puts embeddings under time pressure:
**does the target Postgres support `pgvector`?** The rest of this doc —
service topology, `railway.json`, the SSE service, env var provisioning —
is written as the phases that need it land.

## pgvector

### Dev image (verified)

`CREATE EXTENSION vector;` succeeds against the dev compose Postgres.

- Image: `pgvector/pgvector:pg17`
- Resolved digest at verification time:
  `pgvector/pgvector@sha256:cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f`
- Server: `PostgreSQL 17.11 (Debian 17.11-1.pgdg12+2)`
- Extension version installed: `vector 0.8.6`

```
$ psql -h localhost -p 5433 -U keel -d keel -c "CREATE EXTENSION IF NOT EXISTS vector; SELECT extname, extversion FROM pg_extension WHERE extname='vector';"
CREATE EXTENSION
 extname | extversion
---------+------------
 vector  | 0.8.6
(1 row)
```

### Target host (Railway) — **not directly verified, no Railway account available in this environment**

Checked via Railway's public documentation and community help station
(no account needed for this much):

- **Railway's standard Postgres plugin — the one you get from "Add
  Database → PostgreSQL" — does not include `pgvector` by default.**
  A Railway moderator's stated guidance on the help station is that
  "enabling pgvector isn't as straightforward" on that default service.
  ([Railway Help Station](https://station.railway.com/questions/enable-pgvector-extension-for-postgre-sql-e861e033))
- Railway instead publishes dedicated templates that ship `pgvector`
  pre-installed, e.g. a "pgvector" template and a "PostgreSQL Extensions"
  template (`EXTENSIONS` env var, pre-compiled extensions including
  `vector`). ([Railway: pgvector template](https://railway.com/deploy/pgvector-latest),
  [Railway: PostgreSQL Extensions template](https://railway.com/deploy/postgresql-extensions))
- One of Railway's official pgvector templates runs the same image family
  we use in dev (`pgvector/pgvector`, e.g. `pgvector/pgvector:0.8.6-pg18`),
  which is reassuring for parity but is a **different service** from the
  default Postgres plugin — provisioning the wrong one is the actual risk.

**Open item — the exact question to answer before Phase 5.5, with an
account:**

> When provisioning Postgres for this project on Railway, deploy the
> `pgvector` template (or the PostgreSQL Extensions template with
> `vector` in `EXTENSIONS`) instead of the default "Add Database →
> PostgreSQL" plugin, and confirm `CREATE EXTENSION vector;` succeeds on
> whatever image tag that template resolves to at deploy time. Record
> the resolved image tag/digest here once done, the same way the dev
> image is recorded above.

Do not provision the default Postgres plugin for this project and
discover the gap during Phase 5.5 — the PRD flags this exact trap.

## Everything else

Not written yet. `railway.json`, service topology (api / worker / beat /
the dedicated SSE uvicorn service per the Appendix note on
`text/event-stream` buffering), and env var provisioning arrive with the
phases that need them.

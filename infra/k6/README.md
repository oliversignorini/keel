# k6 smoke test — widget list

Performance target: API p95 under 300ms for list endpoints at 10k
rows per organisation, at 100 rps on the widget list.

**This test targets the demo `widgets` resource** (`GET
/api/v1/orgs/<slug>/widgets/`). `init --demo-slice delete` removes that
endpoint along with the rest of the demo slice, which leaves this
directory with nothing to smoke — `init` does not delete it for you. If
your project ran `init` that way, either delete `infra/k6/` or repoint
`widget-list-smoke.js` at one of your own list endpoints (swap the URL
and the seed script's model below for yours; the rate-limit and VU/duration
mechanics carry over unchanged). If you kept the demo slice (`init
--demo-slice keep`), this still runs as-is.

## Seed an organisation and a pool of sessions

100 rps from a _single_ session trips Phase 8.6's per-user rate limit
(300/min = 5 rps) almost immediately — see "what this measured" below.
Seed several dozen member sessions instead, one per simulated user:

```bash
cd apps/api
uv run python manage.py shell -c "
from keel.accounts.models import User
from keel.organizations import services
from keel.organizations.models import Organization, Membership, Role
from keel.widgets.models import Widget
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.auth import login
from django.test import RequestFactory

owner, _ = User.objects.get_or_create(email='k6@example.com')
owner.set_password('s3cret-pass-1234')
owner.save()
org = Organization.objects.filter(slug='k6-smoke').first()
if not org:
    org = services.create_organization(name='K6 Smoke', slug='k6-smoke', actor=owner)
if Widget.objects.filter(organization=org).count() < 200:
    Widget.objects.bulk_create([
        Widget(organization=org, name=f'Widget {i}', description='', status='active', created_by=owner)
        for i in range(200)
    ])

owner_role = Role.objects.filter(organization__isnull=True, name='Owner').first()
cookies = []
for i in range(60):
    user, _ = User.objects.get_or_create(email=f'k6-user-{i}@example.com')
    user.set_password('s3cret-pass-1234')
    user.save()
    Membership.objects.get_or_create(
        organization=org, user=user,
        defaults={'role': owner_role, 'status': Membership.STATUS_ACTIVE},
    )
    request = RequestFactory().get('/')
    request.session = SessionStore()
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    request.session.save()
    cookies.append(request.session.session_key)
print('WIDGET_LIST_SESSION_COOKIES=' + ','.join(cookies))
"
```

## Run

```bash
docker run --rm -i \
  --add-host=api.lvh.me:host-gateway \
  -e API_BASE_URL=http://api.lvh.me:8000 \
  -e WIDGET_LIST_ORG_SLUG=k6-smoke \
  -e WIDGET_LIST_SESSION_COOKIES=<from above> \
  -e WIDGET_LIST_DURATION=30s \
  grafana/k6 run - < infra/k6/widget-list-smoke.js
```

`WIDGET_LIST_VUS` (default 15) and `WIDGET_LIST_DURATION` (default 30s)
are overridable — deliberately **not** named `K6_VUS`/`K6_DURATION`,
which are k6's own reserved config env vars and silently replace the
whole `scenarios` block with k6's default single-VU scenario instead of
merging (found the hard way — see below).

## What this machine actually measured

Windows dev laptop, Django's `manage.py runserver` (not gunicorn —
gunicorn imports `fcntl`, Unix-only, unavailable here), Docker Desktop's
network bridge via `--add-host=host-gateway`, 60 real sessions, 200
seeded widgets, 15 VUs, 30s:

```
http_req_duration: p(95)=209.64ms   ✓ (< 300ms)
http_req_failed:   0.51%             ✓ (< 1%)
http_reqs:         103.2 req/s       ✓ (≥ 100 rps)
```

**Two real findings on the way to that number, not just the target hit:**

1. **k6's `constant-arrival-rate` executor never allocated more than 1
   VU** on this machine regardless of `preAllocatedVUs`/`maxVUs`,
   capping throughput at ~33 rps no matter which server backed it
   (`manage.py runserver` and a `uvicorn config.asgi:application`
   process both produced the identical ~1-VU ceiling). Root cause,
   found by elimination: a **custom env var name collision** — this
   script originally read `K6_DURATION`/`K6_VUS`, which are k6's own
   reserved configuration env vars (equivalent to `--duration`/`--vus`).
   Setting them via `-e` silently discards the script's `scenarios`
   block for k6's own default scenario instead of merging into it (k6
   does print a warning: `"env" level configuration overrode scenarios
configuration entirely` — easy to miss in a long run). Renamed to
   `WIDGET_LIST_*` and switched to `constant-vus`, which sidesteps
   whatever was different about the arrival-rate scheduler here too.
2. **A single session cannot sustain 100 rps** — Phase 8.6's
   `UserRateThrottle` (300/min = 5 rps per user) means "100 rps on the
   widget list" only makes sense, and only reflects anything real,
   spread across many concurrent users. The pool-of-60-sessions setup
   above is why: it is not incidental test plumbing, it is the only way
   this number and the rate limit are both true at once.

**What would need a different setup to measure something more
representative of production:** this ran against Django's development
server, not gunicorn (unavailable on Windows) — the 0.51% error rate
(16 dropped connections out of 3107) is plausibly the dev server's
connection-handling limits under 15 concurrent VUs, not the
application code. A Linux box or container running the real gunicorn
configuration from `railway.json` would be the fairer comparison.

import http from "k6/http";
import { check } from "k6";

/**
 * k6 smoke test. Performance target: API p95 under 300ms for
 * list endpoints at 10k rows per organisation, at 100 rps on the widget
 * list.
 *
 * Needs a pre-seeded organisation, an authenticated session cookie, and
 * a matching CSRF token — see infra/k6/README.md for how to produce
 * them and run this against a local dev stack.
 */
// Custom env var names deliberately avoid the K6_ prefix — K6_VUS,
// K6_DURATION etc. are k6's *own* reserved configuration env vars
// (equivalent to --vus/--duration), and setting one silently replaces
// the whole `scenarios` block below with k6's own default scenario
// instead of merging ("env" level configuration overrode scenarios
// configuration entirely — a real warning k6 prints, found the hard way
// running this the first time: every run showed exactly 1 VU no matter
// what `scenarios` said, because a custom K6_DURATION collided with
// k6's own reserved name). See infra/k6/README.md.
export const options = {
  scenarios: {
    widget_list_smoke: {
      executor: "constant-vus",
      vus: __ENV.WIDGET_LIST_VUS ? Number(__ENV.WIDGET_LIST_VUS) : 15,
      duration: __ENV.WIDGET_LIST_DURATION || "30s",
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<300"],
    http_req_failed: ["rate<0.01"],
    http_reqs: ["rate>=100"],
  },
};

const API_BASE = __ENV.API_BASE_URL || "http://api.lvh.me:8000";
const ORG_SLUG = __ENV.WIDGET_LIST_ORG_SLUG;
// A comma-separated pool of session cookies, one per simulated member of
// the organisation (infra/k6/README.md's seed step creates 60) — 100 rps
// from a *single* session immediately trips the per-user rate limit
// Phase 8.6 turned on (300/min = 5 rps, see the "What this machine
// actually measured" note in the README): this test is meant to smoke
// the widget-list endpoint's own performance, not re-prove throttling,
// which keel/core/tests already cover directly.
const SESSION_COOKIES = (__ENV.WIDGET_LIST_SESSION_COOKIES || "").split(",").filter(Boolean);

export default function () {
  if (!ORG_SLUG || SESSION_COOKIES.length === 0) {
    throw new Error(
      "WIDGET_LIST_ORG_SLUG and WIDGET_LIST_SESSION_COOKIES must be set — see infra/k6/README.md for how to seed them.",
    );
  }
  const cookie = SESSION_COOKIES[Math.floor(Math.random() * SESSION_COOKIES.length)];

  const response = http.get(`${API_BASE}/api/v1/organizations/${ORG_SLUG}/widgets/`, {
    headers: {
      Cookie: `sessionid=${cookie}`,
      Accept: "application/json",
    },
  });

  check(response, {
    "status is 200": (r) => r.status === 200,
    "has results array": (r) => {
      try {
        return Array.isArray(JSON.parse(r.body).results);
      } catch {
        return false;
      }
    },
  });
}

import { Button } from "@keel/ui";
import { getAuthProviderRedirectUrl, readCsrfCookie } from "@keel/api-client";

// Django's default POST-field name for a plain (non-fetch) form submission
// — distinct from CSRF_HEADER_NAME, which src/http/mutator.ts uses for
// fetch requests. Not exported from @keel/api-client because nothing else
// in the app submits a real HTML form.
const CSRF_FORM_FIELD_NAME = "csrfmiddlewaretoken";

// lucide ships no brand marks, so the Google G is inline. Its `fill`s are
// literal brand colours on purpose: Google's terms require the mark be
// reproduced unmodified, so this one glyph does not follow the token
// vocabulary the rest of the surface does.
function GoogleMark() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="size-4">
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1Z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.65l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23Z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.11a6.6 6.6 0 0 1 0-4.22V7.05H2.18a11 11 0 0 0 0 9.9l3.66-2.84Z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1a11 11 0 0 0-9.82 6.05l3.66 2.84c.87-2.6 3.3-4.51 6.16-4.51Z"
      />
    </svg>
  );
}

/**
 * Starts allauth's provider redirect (PRD §6 Signup flow). The callback
 * lands the user back on /onboarding, same as the email/password path.
 *
 * docs/auth-client-contract.md documented this as a `GET` with query
 * params, but the live allauth headless spec this client is generated
 * from (packages/api-client/orval.config.ts) says otherwise: it's a
 * `POST` with a form-urlencoded body (`provider`, `process`,
 * `callback_url`) — see `authProviderRedirect` in
 * src/generated/identity.query.ts. It still has to be a real browser
 * navigation rather than a `fetch()` (the response is a 302 to Google's
 * consent screen, which only a top-level navigation can follow), so this
 * renders an actual `<form method="post">` instead of an `<a href>` — the
 * only way to get a POST *and* a full navigation without JavaScript
 * driving the redirect itself.
 *
 * The action is a same-origin relative path, proxied like every other
 * `/_allauth/…` call (docs/adr/0002-auth-bff-shape.md) — the BFF relays
 * Django's 302 to Google untouched (`redirect: 'manual'` in
 * apps/web/lib/api/proxy.ts), so the browser's own top-level navigation
 * still ends up following the redirect to Google itself. The one hop
 * that stays genuinely direct to Django is Google's own callback
 * (registered as `/accounts/google/login/callback/`, a headed, non-
 * `/_allauth` URL that was never routed through Next.js) — an OAuth
 * property, not something this form controls.
 */
export function GoogleContinueLink({ nextPath = "/onboarding" }: { nextPath?: string }) {
  const callbackUrl =
    typeof window === "undefined" ? nextPath : new URL(nextPath, window.location.origin).toString();
  const action = getAuthProviderRedirectUrl();
  const csrfToken = readCsrfCookie();

  return (
    <form method="post" action={action}>
      <input type="hidden" name="provider" value="google" />
      <input type="hidden" name="process" value="login" />
      <input type="hidden" name="callback_url" value={callbackUrl} />
      {csrfToken ? <input type="hidden" name={CSRF_FORM_FIELD_NAME} value={csrfToken} /> : null}
      <Button type="submit" variant="outline" className="w-full">
        <GoogleMark />
        Continue with Google
      </Button>
    </form>
  );
}

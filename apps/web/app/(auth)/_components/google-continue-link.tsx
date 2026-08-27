import { getAuthProviderRedirectUrl, readCsrfCookie } from "@keel/api-client";

// Django's default POST-field name for a plain (non-fetch) form submission
// — distinct from CSRF_HEADER_NAME, which src/http/mutator.ts uses for
// fetch requests. Not exported from @keel/api-client because nothing else
// in the app submits a real HTML form.
const CSRF_FORM_FIELD_NAME = "csrfmiddlewaretoken";

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
      <button
        type="submit"
        className="flex w-full items-center justify-center gap-2 rounded-md border border-neutral-300 px-4 py-2 text-sm font-medium text-neutral-900 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-100 dark:hover:bg-neutral-800"
      >
        Continue with Google
      </button>
    </form>
  );
}

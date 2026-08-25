import { API_BASE_URL, getAuthProviderRedirectUrl } from "@keel/api-client";

/**
 * Starts allauth's provider redirect (PRD §6 Signup flow). The callback
 * lands the user back on /onboarding, same as the email/password path —
 * onboarding itself is Phase 3 and 404s until that lands (B.2).
 */
export function GoogleContinueLink({ nextPath = "/onboarding" }: { nextPath?: string }) {
  const callbackUrl =
    typeof window === "undefined" ? nextPath : new URL(nextPath, window.location.origin).toString();
  const href = `${API_BASE_URL}${getAuthProviderRedirectUrl({
    provider: "google",
    process: "login",
    callback_url: callbackUrl,
  })}`;

  return (
    <a
      href={href}
      className="flex items-center justify-center gap-2 rounded-md border border-neutral-300 px-4 py-2 text-sm font-medium text-neutral-900 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-100 dark:hover:bg-neutral-800"
    >
      Continue with Google
    </a>
  );
}

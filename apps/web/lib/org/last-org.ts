export const LAST_ORG_STORAGE_KEY = "keel:lastOrgSlug";

export function rememberLastOrg(slug: string): void {
  try {
    window.localStorage.setItem(LAST_ORG_STORAGE_KEY, slug);
  } catch {
    // Storage can be unavailable (private browsing, quota) — losing the
    // "last used" preference is harmless; /app falls back to the first
    // organisation in that case.
  }
}

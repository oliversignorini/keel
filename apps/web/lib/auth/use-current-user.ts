"use client";

import { UnauthorizedError, authGetSession, type AuthenticatedUser } from "@keel/api-client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

interface UseCurrentUserResult {
  user: AuthenticatedUser | null;
  loading: boolean;
}

/**
 * The API is the enforcement point, not middleware (see middleware.ts) — a
 * session cookie can be present but expired. Every /account page uses this
 * hook rather than trusting middleware, and sends a real 401 to /login.
 */
export function useCurrentUser(): UseCurrentUserResult {
  const router = useRouter();
  const [user, setUser] = useState<AuthenticatedUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    authGetSession()
      .then((result) => {
        if (cancelled) return;
        // The mutator throws on non-2xx (see identityFetch), so the only
        // variant that ever reaches here is the status: 200 one — narrow
        // on it to satisfy the generated union type.
        setUser(result.status === 200 ? (result.data.data?.user ?? null) : null);
        setLoading(false);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        if (error instanceof UnauthorizedError) {
          router.push(`/login?next=${encodeURIComponent(window.location.pathname)}`);
          return;
        }
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [router]);

  return { user, loading };
}

"use client";

import { useCurrentUser } from "@/lib/auth/use-current-user";

export default function ProfilePage() {
  const { user, loading } = useCurrentUser();

  if (loading) {
    return (
      <p role="status" className="text-sm text-neutral-600 dark:text-neutral-400">
        Loading…
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">Profile</h1>
      <dl className="text-sm">
        <dt className="font-medium text-neutral-700 dark:text-neutral-300">Email</dt>
        <dd className="text-neutral-900 dark:text-neutral-100">{user?.email ?? "—"}</dd>
      </dl>
      <p className="text-sm text-neutral-500 dark:text-neutral-500">
        Editable profile fields and organisation membership arrive in Phase 3.
      </p>
    </div>
  );
}

"use client";

import { ApiError, sessionsList, sessionsRevoke, type SessionItem } from "@keel/api-client";
import { useEffect, useState } from "react";

import { FormError } from "../../(auth)/_components/form-error";

export default function SessionsPage() {
  const [sessions, setSessions] = useState<SessionItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const result = await sessionsList();
      setSessions(result.data.data ?? []);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load sessions.");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function revoke(sessionId: string) {
    setError(null);
    try {
      await sessionsRevoke({ sessions: [sessionId] });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not revoke that session.");
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        Active sessions
      </h1>
      <FormError message={error} />
      {sessions === null ? (
        <p role="status" className="text-sm text-neutral-600 dark:text-neutral-400">
          Loading…
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {sessions.map((session) => (
            <li
              key={session.id}
              className="flex items-center justify-between rounded-md border border-neutral-200 px-3 py-2 text-sm dark:border-neutral-800"
            >
              <div>
                <p className="text-neutral-900 dark:text-neutral-100">
                  {session.user_agent ?? "Unknown device"}{" "}
                  {session.is_current ? "(this device)" : ""}
                </p>
                <p className="text-neutral-500 dark:text-neutral-500">
                  {session.ip} · last seen {session.last_seen_at}
                </p>
              </div>
              {session.is_current || !session.id ? null : (
                <button
                  type="button"
                  onClick={() => revoke(session.id!)}
                  className="text-red-600 underline dark:text-red-400"
                >
                  Revoke
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

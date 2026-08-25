"use client";

import { authGetSession } from "@keel/api-client";
import { toAppHost } from "@/lib/host";
import { acceptInvitation, resolveInvitation } from "@/lib/org/api";
import type { InviteResolveResponse } from "@/lib/org/types";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { SubmitButton } from "../../_components/submit-button";

/**
 * `/invite/[token]` (PRD §5 Routes, §6 "Invitation"; phase-3.md Worktree
 * C: "all four outcomes, with copy that does not leak").
 *
 * All four outcomes are driven by two calls, never more:
 *
 * 1. `GET /api/v1/invite/{token}/` (resolveInvitation) — 200 with
 *    `{ organization, email, requires_signup }` for a token that is
 *    neither expired, revoked, nor accepted; 409 `invalid_or_expired`
 *    otherwise. Expired, revoked, and nonexistent all take this one path
 *    (organizations/viewsets.py `InvitationAcceptView._resolve_valid`) —
 *    that's what makes them indistinguishable to the recipient.
 * 2. `POST /api/v1/invite/{token}/` (acceptInvitation) — only ever called
 *    when the signed-in user's email already matches the resolved
 *    `email`, so "wrong email" is never learned from this call; it is
 *    read straight off the GET response instead. The GET response already
 *    discloses `email` to whoever holds a token that is still valid — the
 *    outcome below just renders that fact rather than a second lookup.
 */

type Outcome =
  | { kind: "loading" }
  | { kind: "invalid" }
  | { kind: "requires_signup"; invite: InviteResolveResponse }
  | { kind: "wrong_email"; invite: InviteResolveResponse; currentEmail: string }
  | { kind: "ready_to_accept"; invite: InviteResolveResponse }
  | { kind: "accepted"; orgSlug: string }
  | { kind: "accept_failed" };

export default function InvitePage() {
  const params = useParams<{ token: string }>();
  const [outcome, setOutcome] = useState<Outcome>({ kind: "loading" });
  const [accepting, setAccepting] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function resolve() {
      let invite: InviteResolveResponse;
      try {
        invite = await resolveInvitation(params.token);
      } catch {
        // 409 invalid_or_expired covers expired, revoked, and nonexistent
        // alike — see this file's docstring.
        if (!cancelled) {
          setOutcome({ kind: "invalid" });
        }
        return;
      }

      if (cancelled) return;

      if (invite.requires_signup) {
        setOutcome({ kind: "requires_signup", invite });
        return;
      }

      let currentEmail: string | null = null;
      try {
        const session = await authGetSession();
        currentEmail = session.status === 200 ? (session.data.data?.user?.email ?? null) : null;
      } catch {
        currentEmail = null;
      }

      if (cancelled) return;

      if (!currentEmail) {
        // Session expired between the server's "signed in" answer and now
        // — treat it the same as "not signed in".
        setOutcome({ kind: "requires_signup", invite });
        return;
      }

      if (currentEmail.toLowerCase() !== invite.email.toLowerCase()) {
        setOutcome({ kind: "wrong_email", invite, currentEmail });
        return;
      }

      setOutcome({ kind: "ready_to_accept", invite });
    }

    void resolve();
    return () => {
      cancelled = true;
    };
  }, [params.token]);

  async function accept() {
    if (outcome.kind !== "ready_to_accept") return;
    const orgSlug = outcome.invite.organization.slug;
    setAccepting(true);
    try {
      await acceptInvitation(params.token);
      setOutcome({ kind: "accepted", orgSlug });
      window.location.href = `${window.location.protocol}//${toAppHost(window.location.host)}/${orgSlug}`;
    } catch {
      setOutcome({ kind: "accept_failed" });
    } finally {
      setAccepting(false);
    }
  }

  if (outcome.kind === "loading") {
    return (
      <p role="status" className="text-sm text-neutral-600 dark:text-neutral-400">
        Checking your invitation…
      </p>
    );
  }

  if (outcome.kind === "invalid" || outcome.kind === "accept_failed") {
    return (
      <>
        <h1 className="mb-2 text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          This invitation is no longer valid
        </h1>
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          Ask an admin to send you a new one.
        </p>
      </>
    );
  }

  if (outcome.kind === "requires_signup") {
    const signupHref = `/signup?email=${encodeURIComponent(outcome.invite.email)}&next=${encodeURIComponent(`/invite/${params.token}`)}`;
    const loginHref = `/login?next=${encodeURIComponent(`/invite/${params.token}`)}`;
    return (
      <>
        <h1 className="mb-2 text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          You&apos;ve been invited to {outcome.invite.organization.name}
        </h1>
        <p className="mb-6 text-sm text-neutral-600 dark:text-neutral-400">
          Create an account with {outcome.invite.email} to accept.
        </p>
        <div className="flex flex-col gap-2">
          <Link
            href={signupHref}
            className="rounded-md bg-neutral-900 px-4 py-2 text-center text-sm font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
          >
            Create account
          </Link>
          <Link href={loginHref} className="text-center text-sm underline">
            Already have an account? Log in
          </Link>
        </div>
      </>
    );
  }

  if (outcome.kind === "wrong_email") {
    return (
      <>
        <h1 className="mb-2 text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          Wrong account
        </h1>
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          This invitation is for {outcome.invite.email}, but you&apos;re signed in as{" "}
          {outcome.currentEmail}.
        </p>
      </>
    );
  }

  // ready_to_accept | accepted
  return (
    <>
      <h1 className="mb-2 text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        Join {outcome.kind === "ready_to_accept" ? outcome.invite.organization.name : ""}
      </h1>
      <p className="mb-6 text-sm text-neutral-600 dark:text-neutral-400">
        You&apos;re signed in with the invited email.
      </p>
      <SubmitButton type="button" onClick={accept} disabled={accepting}>
        {accepting ? "Joining…" : "Accept invitation"}
      </SubmitButton>
    </>
  );
}

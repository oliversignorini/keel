"use client";

import {
  ApiError,
  NotFoundError,
  UnauthorizedError,
  authReauthenticate,
  identityFetch,
} from "@keel/api-client";
import { useEffect, useState } from "react";

import { FormError } from "../../(auth)/_components/form-error";
import { FormField } from "../../(auth)/_components/form-field";
import { SubmitButton } from "../../(auth)/_components/submit-button";

type TotpState =
  | { status: "loading" }
  | { status: "unavailable" }
  | { status: "inactive"; provisioningUri: string }
  | { status: "active" };

// `/_allauth/browser/v1/account/authenticators/totp` only exists in the
// generated client's spec when `KEEL_MFA_ENABLED` is on at generation time
// (docs/auth-client-contract.md) — it's off by default,
// so `packages/api-client` has no typed `totpGet`/`totpActivate`/
// `totpDeactivate` to import right now. This calls the same routes
// directly through the generated transport (identityFetch — same CSRF
// handling, same typed errors). The 404-means-unavailable handling below
// is unchanged from before this file used raw paths: a 404 here already
// covered both "not enrolled" and "the flag is off", so nothing about the
// user-facing behaviour changes when the flag is eventually turned on and
// this switches back to the generated functions.
const TOTP_PATH = "/_allauth/browser/v1/account/authenticators/totp";

interface TotpGetResponse {
  data?: { provisioning_uri?: string };
}

export function TotpSection() {
  const [state, setState] = useState<TotpState>({ status: "loading" });
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  // allauth >= 65.20 no longer counts a recent login as reauthentication, so
  // enabling/disabling answers 401 until the user re-enters their password.
  const [reauthFor, setReauthFor] = useState<"activate" | "deactivate" | null>(null);
  const [password, setPassword] = useState("");

  useEffect(() => {
    let cancelled = false;

    identityFetch<{ data: TotpGetResponse }>(TOTP_PATH)
      .then((result) => {
        if (cancelled) return;
        const provisioningUri = result.data.data?.provisioning_uri;
        setState(provisioningUri ? { status: "inactive", provisioningUri } : { status: "active" });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        // 404 covers both "not enrolled" and "the settings flag is off" —
        // the client can't distinguish the two without the flag exposed
        // somewhere. Both read the same to a user: MFA isn't available.
        setState(
          err instanceof NotFoundError ? { status: "unavailable" } : { status: "unavailable" },
        );
      });

    return () => {
      cancelled = true;
    };
  }, []);

  async function activate() {
    setError(null);
    try {
      await identityFetch(TOTP_PATH, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      setState({ status: "active" });
      setCode("");
      setReauthFor(null);
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        setReauthFor("activate");
        return;
      }
      setError(
        err instanceof ApiError ? err.message : "Could not activate two-factor authentication.",
      );
    }
  }

  async function deactivate() {
    setError(null);
    try {
      await identityFetch(TOTP_PATH, { method: "DELETE" });
      setState({ status: "unavailable" });
      setReauthFor(null);
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        setReauthFor("deactivate");
        return;
      }
      setError(
        err instanceof ApiError ? err.message : "Could not deactivate two-factor authentication.",
      );
    }
  }

  async function confirmPassword() {
    setError(null);
    try {
      await authReauthenticate({ password });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not confirm your password.");
      return;
    }
    setPassword("");
    await (reauthFor === "deactivate" ? deactivate() : activate());
  }

  if (reauthFor) {
    return (
      <div className="flex flex-col gap-3">
        <FormError message={error} />
        <p className="text-sm text-muted-foreground">Confirm your password to continue.</p>
        <FormField
          label="Password"
          id="totp-reauth-password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <SubmitButton type="button" onClick={confirmPassword} className="self-start">
          Confirm password
        </SubmitButton>
      </div>
    );
  }

  if (state.status === "loading") {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Loading…
      </p>
    );
  }

  if (state.status === "unavailable") {
    return (
      <p className="text-sm text-muted-foreground">
        Two-factor authentication is not available for this account.
      </p>
    );
  }

  if (state.status === "active") {
    return (
      <div className="flex flex-col gap-2">
        <p className="text-sm text-chart-2">Two-factor authentication is enabled.</p>
        <FormError message={error} />
        <button
          type="button"
          onClick={deactivate}
          className="self-start text-sm text-destructive underline"
        >
          Disable
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <FormError message={error} />
      <p className="text-sm text-muted-foreground">
        Add this key to your authenticator app, then enter the 6-digit code it generates.
      </p>
      <code className="break-all rounded-md bg-muted px-3 py-2 text-xs">
        {state.provisioningUri}
      </code>
      <FormField
        label="Code"
        id="totp-code"
        type="text"
        inputMode="numeric"
        maxLength={6}
        value={code}
        onChange={(event) => setCode(event.target.value)}
      />
      <SubmitButton type="button" onClick={activate} className="self-start">
        Enable
      </SubmitButton>
    </div>
  );
}

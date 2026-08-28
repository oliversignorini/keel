"use client";

import { applyFieldErrors } from "@/lib/api/form-error-mapper";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  ApiError,
  NotFoundError,
  accountPasswordChange,
  identityFetch,
  identitySchemas,
} from "@keel/api-client";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";

import { FormError } from "../../(auth)/_components/form-error";
import { FormField } from "../../(auth)/_components/form-field";
import { SubmitButton } from "../../(auth)/_components/submit-button";

type PasswordFormValues = z.infer<typeof identitySchemas.accountPasswordChangeBody>;

function PasswordChangeForm() {
  const [formError, setFormError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<PasswordFormValues>({
    resolver: zodResolver(identitySchemas.accountPasswordChangeBody),
  });

  async function onSubmit(values: PasswordFormValues) {
    setFormError(null);
    setSuccess(false);
    try {
      await accountPasswordChange(values);
      setSuccess(true);
      reset();
    } catch (error) {
      setFormError(applyFieldErrors(error, setError));
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
      <FormError message={formError} />
      {success ? (
        <p className="text-sm text-green-700 dark:text-green-400">Password changed.</p>
      ) : null}
      <FormField
        label="Current password"
        id="current_password"
        type="password"
        autoComplete="current-password"
        error={errors.current_password?.message}
        {...register("current_password")}
      />
      <FormField
        label="New password"
        id="new_password"
        type="password"
        autoComplete="new-password"
        error={errors.new_password?.message}
        {...register("new_password")}
      />
      <SubmitButton disabled={isSubmitting} className="self-start">
        {isSubmitting ? "Saving…" : "Change password"}
      </SubmitButton>
    </form>
  );
}

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

function TotpSection() {
  const [state, setState] = useState<TotpState>({ status: "loading" });
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);

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
    } catch (err) {
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
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not deactivate two-factor authentication.",
      );
    }
  }

  if (state.status === "loading") {
    return (
      <p role="status" className="text-sm text-neutral-600 dark:text-neutral-400">
        Loading…
      </p>
    );
  }

  if (state.status === "unavailable") {
    return (
      <p className="text-sm text-neutral-500 dark:text-neutral-500">
        Two-factor authentication is not available for this account.
      </p>
    );
  }

  if (state.status === "active") {
    return (
      <div className="flex flex-col gap-2">
        <p className="text-sm text-green-700 dark:text-green-400">
          Two-factor authentication is enabled.
        </p>
        <FormError message={error} />
        <button
          type="button"
          onClick={deactivate}
          className="self-start text-sm text-red-600 underline dark:text-red-400"
        >
          Disable
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <FormError message={error} />
      <p className="text-sm text-neutral-600 dark:text-neutral-400">
        Add this key to your authenticator app, then enter the 6-digit code it generates.
      </p>
      <code className="break-all rounded-md bg-neutral-100 px-3 py-2 text-xs dark:bg-neutral-800">
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

export default function SecurityPage() {
  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-4">
        <h1 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">Password</h1>
        <PasswordChangeForm />
      </section>
      <section className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          Two-factor authentication
        </h2>
        <TotpSection />
      </section>
    </div>
  );
}

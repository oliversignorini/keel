"use client";

import { applyFieldErrors } from "@/lib/api/form-error-mapper";
import { zodResolver } from "@hookform/resolvers/zod";
import { identityFetch } from "@keel/api-client";
import {
  Alert,
  AlertDescription,
  Button,
  Form,
  FormControl,
  FormItem,
  FormLabel,
  FormMessage,
  Input,
  RHFFormField,
} from "@keel/ui";
import { AlertCircle, Loader2 } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { defaultAppUrl, navigateTo } from "@/lib/navigation";

// `POST /_allauth/browser/v1/auth/2fa/authenticate` only exists in the
// generated client's spec when `KEEL_MFA_ENABLED` is on at generation
// time (docs/auth-client-contract.md "MFA endpoints") — it's off by
// default — MFA is scaffolded and disabled by a settings flag — so
// `packages/api-client` has no typed `authMfaAuthenticate` or
// `identitySchemas.authMfaAuthenticateBody` to import right now. This
// calls the same route directly through the generated transport
// (identityFetch — same CSRF handling, same typed errors) with a
// hand-written schema instead. Once the flag is on for a real project,
// `pnpm generate` produces the typed function and this file should switch
// back to it.
const mfaFormSchema = z.object({ code: z.string().min(1, "Enter your authenticator code.") });
type MfaFormValues = z.infer<typeof mfaFormSchema>;

export default function MfaChallengePage() {
  return (
    <Suspense>
      <MfaChallengeForm />
    </Suspense>
  );
}

function MfaChallengeForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<MfaFormValues>({
    resolver: zodResolver(mfaFormSchema),
    defaultValues: { code: "" },
  });
  const { isSubmitting } = form.formState;

  async function onSubmit(values: MfaFormValues) {
    setFormError(null);
    try {
      await identityFetch("/_allauth/browser/v1/auth/2fa/authenticate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });
      navigateTo(router, searchParams.get("next") ?? defaultAppUrl());
    } catch (error) {
      setFormError(applyFieldErrors(error, form.setError));
    }
  }

  return (
    <>
      <h1 className="mb-2 text-lg font-semibold text-foreground">Two-factor authentication</h1>
      <p className="mb-6 text-sm text-muted-foreground">
        Enter the 6-digit code from your authenticator app.
      </p>
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
          {formError ? (
            <Alert variant="destructive">
              <AlertCircle />
              <AlertDescription>{formError}</AlertDescription>
            </Alert>
          ) : null}
          <RHFFormField
            control={form.control}
            name="code"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Code</FormLabel>
                <FormControl>
                  <Input
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={6}
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? <Loader2 className="animate-spin" /> : null}
            {isSubmitting ? "Verifying…" : "Verify"}
          </Button>
        </form>
      </Form>
    </>
  );
}

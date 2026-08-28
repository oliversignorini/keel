"use client";

import { applyFieldErrors } from "@/lib/api/form-error-mapper";
import { zodResolver } from "@hookform/resolvers/zod";
import { UnauthorizedError, authSignup, identitySchemas } from "@keel/api-client";
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
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";

import { navigateTo } from "@/lib/navigation";

import { GoogleContinueLink } from "../_components/google-continue-link";

type SignupFormValues = z.infer<typeof identitySchemas.authSignupBody>;

// useSearchParams() opts the page out of static rendering unless wrapped in
// its own Suspense boundary, same as /login (see that page's comment).
export default function SignupPage() {
  return (
    <Suspense>
      <SignupForm />
    </Suspense>
  );
}

function SignupForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // Invitation-driven signup (PRD §6 "Invitation": "not signed in → signup,
  // prefilled + locked email, then re-resolve") — the email comes from the
  // invite page's already-resolved invitation, never typed by the visitor,
  // so it's locked rather than merely prefilled.
  const lockedEmail = searchParams.get("email");
  const next = searchParams.get("next");
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<SignupFormValues>({
    resolver: zodResolver(identitySchemas.authSignupBody),
    defaultValues: { email: lockedEmail ?? "", password: "" },
  });
  const { isSubmitting } = form.formState;

  async function onSubmit(values: SignupFormValues) {
    setFormError(null);
    try {
      await authSignup(values);
      navigateTo(router, next ?? "/onboarding");
    } catch (error) {
      if (error instanceof UnauthorizedError && error.code === "verify_email") {
        router.push(next ? `/verify-email?next=${encodeURIComponent(next)}` : "/verify-email");
        return;
      }
      setFormError(applyFieldErrors(error, form.setError));
    }
  }

  return (
    <>
      <h1 className="mb-6 text-lg font-semibold text-foreground">Create an account</h1>
      <div className="flex flex-col gap-4">
        {lockedEmail ? null : (
          <>
            <GoogleContinueLink nextPath={next ?? "/onboarding"} />
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <div className="h-px flex-1 bg-border" />
              or
              <div className="h-px flex-1 bg-border" />
            </div>
          </>
        )}
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
              name="email"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Email</FormLabel>
                  <FormControl>
                    <Input
                      type="email"
                      autoComplete="email"
                      readOnly={Boolean(lockedEmail)}
                      aria-readonly={lockedEmail ? true : undefined}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <RHFFormField
              control={form.control}
              name="password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Password</FormLabel>
                  <FormControl>
                    <Input type="password" autoComplete="new-password" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? <Loader2 className="animate-spin" /> : null}
              {isSubmitting ? "Creating account…" : "Sign up"}
            </Button>
          </form>
        </Form>
      </div>
      <p className="mt-4 text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link href="/login" className="underline">
          Log in
        </Link>
      </p>
    </>
  );
}

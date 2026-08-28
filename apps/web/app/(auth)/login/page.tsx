"use client";

import { applyFieldErrors } from "@/lib/api/form-error-mapper";
import { zodResolver } from "@hookform/resolvers/zod";
import { UnauthorizedError, authLogin } from "@keel/api-client";
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
import { z } from "zod";

import { defaultAppUrl, navigateTo } from "@/lib/navigation";

import { GoogleContinueLink } from "../_components/google-continue-link";

// The generated authLoginBody schema (identitySchemas) types the real
// allauth request body — { password } & (username | email | phone) —
// because headless login is generically multi-method. This project's
// User.USERNAME_FIELD is email (PRD §4 "Custom User ... email as
// USERNAME_FIELD"), so email is the only method this form ever needs; a
// narrower local schema keeps the form's field errors typed directly
// against `email` instead of fighting the union. `{email, password}`
// still satisfies the generated body type at the `authLogin()` call below.
const loginFormSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});
type LoginFormValues = z.infer<typeof loginFormSchema>;

// useSearchParams() opts the page out of static rendering unless wrapped in
// its own Suspense boundary (Next.js requires this even though the /login
// route is never actually prerendered as static HTML — it needs the
// session cookie).
export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<LoginFormValues>({
    resolver: zodResolver(loginFormSchema),
    defaultValues: { email: "", password: "" },
  });
  const { isSubmitting } = form.formState;

  async function onSubmit(values: LoginFormValues) {
    setFormError(null);
    try {
      await authLogin(values);
      navigateTo(router, searchParams.get("next") ?? defaultAppUrl());
    } catch (error) {
      if (error instanceof UnauthorizedError && error.code === "mfa_authenticate") {
        const mfaNext = searchParams.get("next");
        router.push(mfaNext ? `/mfa?next=${encodeURIComponent(mfaNext)}` : "/mfa");
        return;
      }
      setFormError(applyFieldErrors(error, form.setError));
    }
  }

  return (
    <>
      <h1 className="mb-6 text-lg font-semibold text-foreground">Log in</h1>
      <div className="flex flex-col gap-4">
        <GoogleContinueLink nextPath={searchParams.get("next") ?? defaultAppUrl()} />
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <div className="h-px flex-1 bg-border" />
          or
          <div className="h-px flex-1 bg-border" />
        </div>
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
                    <Input type="email" autoComplete="email" {...field} />
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
                    <Input type="password" autoComplete="current-password" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? <Loader2 className="animate-spin" /> : null}
              {isSubmitting ? "Logging in…" : "Log in"}
            </Button>
          </form>
        </Form>
      </div>
      <p className="mt-4 flex justify-between text-sm text-muted-foreground">
        <Link href="/signup" className="underline">
          Create an account
        </Link>
        <Link href="/reset-password" className="underline">
          Forgot password?
        </Link>
      </p>
    </>
  );
}

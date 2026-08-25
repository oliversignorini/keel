"use client";

import { applyFieldErrors } from "@/lib/api/form-error-mapper";
import { zodResolver } from "@hookform/resolvers/zod";
import { UnauthorizedError, authLogin } from "@keel/api-client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { FormError } from "../_components/form-error";
import { FormField } from "../_components/form-field";
import { GoogleContinueLink } from "../_components/google-continue-link";
import { SubmitButton } from "../_components/submit-button";

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
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({ resolver: zodResolver(loginFormSchema) });

  async function onSubmit(values: LoginFormValues) {
    setFormError(null);
    try {
      await authLogin(values);
      router.push(searchParams.get("next") ?? "/app");
    } catch (error) {
      if (error instanceof UnauthorizedError && error.code === "mfa_authenticate") {
        router.push("/mfa");
        return;
      }
      setFormError(applyFieldErrors(error, setError));
    }
  }

  return (
    <>
      <h1 className="mb-6 text-lg font-semibold text-neutral-900 dark:text-neutral-100">Log in</h1>
      <div className="flex flex-col gap-4">
        <GoogleContinueLink nextPath={searchParams.get("next") ?? "/app"} />
        <div className="flex items-center gap-3 text-xs text-neutral-500">
          <div className="h-px flex-1 bg-neutral-200 dark:bg-neutral-800" />
          or
          <div className="h-px flex-1 bg-neutral-200 dark:bg-neutral-800" />
        </div>
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
          <FormError message={formError} />
          <FormField
            label="Email"
            id="email"
            type="email"
            autoComplete="email"
            error={errors.email?.message}
            {...register("email")}
          />
          <FormField
            label="Password"
            id="password"
            type="password"
            autoComplete="current-password"
            error={errors.password?.message}
            {...register("password")}
          />
          <SubmitButton disabled={isSubmitting}>
            {isSubmitting ? "Logging in…" : "Log in"}
          </SubmitButton>
        </form>
      </div>
      <p className="mt-4 flex justify-between text-sm text-neutral-600 dark:text-neutral-400">
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

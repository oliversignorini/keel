"use client";

import { applyFieldErrors } from "@/lib/api/form-error-mapper";
import { zodResolver } from "@hookform/resolvers/zod";
import { authPasswordReset, identitySchemas } from "@keel/api-client";
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
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";

import { defaultAppUrl, navigateTo } from "@/lib/navigation";

const passwordSchema = identitySchemas.authPasswordResetBody.pick({ password: true });
type PasswordFormValues = z.infer<typeof passwordSchema>;

export default function ResetPasswordKeyPage() {
  const router = useRouter();
  const params = useParams<{ key: string }>();
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<PasswordFormValues>({
    resolver: zodResolver(passwordSchema),
    defaultValues: { password: "" },
  });
  const { isSubmitting } = form.formState;

  async function onSubmit(values: PasswordFormValues) {
    setFormError(null);
    try {
      // See the analogous decode in verify-email/[key]/page.tsx: Next.js
      // does not decode dynamic route segments, and allauth's reset key
      // can itself contain percent-encoded characters.
      await authPasswordReset({ key: decodeURIComponent(params.key), password: values.password });
      navigateTo(router, defaultAppUrl());
    } catch (error) {
      setFormError(applyFieldErrors(error, form.setError));
    }
  }

  return (
    <>
      <h1 className="mb-6 text-lg font-semibold text-foreground">Choose a new password</h1>
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
            name="password"
            render={({ field }) => (
              <FormItem>
                <FormLabel>New password</FormLabel>
                <FormControl>
                  <Input type="password" autoComplete="new-password" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? <Loader2 className="animate-spin" /> : null}
            {isSubmitting ? "Saving…" : "Set new password"}
          </Button>
        </form>
      </Form>
    </>
  );
}

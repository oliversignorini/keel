"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ApiError, authPasswordRequest, identitySchemas } from "@keel/api-client";
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
import { useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";

type RequestFormValues = z.infer<typeof identitySchemas.authPasswordRequestBody>;

export default function ResetPasswordRequestPage() {
  const [formError, setFormError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const form = useForm<RequestFormValues>({
    resolver: zodResolver(identitySchemas.authPasswordRequestBody),
    defaultValues: { email: "" },
  });
  const { isSubmitting } = form.formState;

  async function onSubmit(values: RequestFormValues) {
    setFormError(null);
    try {
      await authPasswordRequest(values);
      // No email-existence disclosure either way (PRD §6 Invitation applies
      // the same principle) — success is shown regardless of the outcome.
      setSent(true);
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : "Something went wrong. Try again.");
    }
  }

  if (sent) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        If an account exists for that email, a reset link is on its way.
      </p>
    );
  }

  return (
    <>
      <h1 className="mb-6 text-lg font-semibold text-foreground">Reset your password</h1>
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
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? <Loader2 className="animate-spin" /> : null}
            {isSubmitting ? "Sending…" : "Send reset link"}
          </Button>
        </form>
      </Form>
      <p className="mt-4 text-sm text-muted-foreground">
        <Link href="/login" className="underline">
          Back to login
        </Link>
      </p>
    </>
  );
}

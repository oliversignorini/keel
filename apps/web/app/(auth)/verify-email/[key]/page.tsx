"use client";

import { ApiError, authEmailVerify } from "@keel/api-client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

type Status = "verifying" | "success" | "error";

export default function VerifyEmailKeyPage() {
  const router = useRouter();
  const params = useParams<{ key: string }>();
  const [status, setStatus] = useState<Status>("verifying");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    authEmailVerify({ key: params.key })
      .then(() => {
        if (cancelled) return;
        setStatus("success");
        router.push("/onboarding");
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setStatus("error");
        setMessage(
          error instanceof ApiError ? error.message : "This link is invalid or has expired.",
        );
      });

    return () => {
      cancelled = true;
    };
  }, [params.key, router]);

  if (status === "verifying") {
    return (
      <p role="status" className="text-sm text-neutral-600 dark:text-neutral-400">
        Verifying your email…
      </p>
    );
  }

  if (status === "success") {
    return (
      <p role="status" className="text-sm text-neutral-600 dark:text-neutral-400">
        Email verified. Redirecting…
      </p>
    );
  }

  return (
    <>
      <h1 className="mb-2 text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        Verification failed
      </h1>
      <p role="alert" className="mb-4 text-sm text-red-600 dark:text-red-400">
        {message}
      </p>
      <Link href="/login" className="text-sm underline">
        Back to login
      </Link>
    </>
  );
}

"use client";

import { ApiError, authEmailVerify } from "@keel/api-client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

type Status = "verifying" | "success" | "error";

export default function VerifyEmailKeyPage() {
  const router = useRouter();
  const params = useParams<{ key: string }>();
  const [status, setStatus] = useState<Status>("verifying");
  const [message, setMessage] = useState<string | null>(null);
  // The key is single-use (allauth invalidates it on first verify), so
  // this effect must call authEmailVerify at most once per key even
  // though React 18 Strict Mode double-invokes effects in development —
  // a second call for the same key would reuse an already-consumed key
  // and fail with invalid_or_expired_key. `startedKey` (not per-run state)
  // makes the network call single-flight across both invocations;
  // `cancelledRef` is likewise shared so the first invocation's real
  // in-flight request still gets to update state once Strict Mode's
  // synchronous mount→cleanup→remount settles back on "not cancelled".
  const startedKey = useRef<string | null>(null);
  const cancelledRef = useRef(false);

  useEffect(() => {
    cancelledRef.current = false;

    if (startedKey.current !== params.key) {
      startedKey.current = params.key;
      authEmailVerify({ key: params.key })
        .then(() => {
          if (cancelledRef.current) return;
          setStatus("success");
          router.push("/onboarding");
        })
        .catch((error: unknown) => {
          if (cancelledRef.current) return;
          setStatus("error");
          setMessage(
            error instanceof ApiError ? error.message : "This link is invalid or has expired.",
          );
        });
    }

    return () => {
      cancelledRef.current = true;
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

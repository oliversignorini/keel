"use client";

import { ApiError, authEmailVerify } from "@keel/api-client";
import { Alert, AlertDescription } from "@keel/ui";
import { AlertCircle, Loader2 } from "lucide-react";
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
      // The `[key]` dynamic segment carries allauth's activation key
      // verbatim from the emailed link, which is percent-encoded (it
      // contains ":") — Next.js does not decode dynamic segments, so
      // params.key here is still e.g. "MTU%3A1wyu…". Decode before
      // sending it on; the raw encoded string fails allauth's HMAC
      // signature check and comes back "invalid_or_expired_key".
      authEmailVerify({ key: decodeURIComponent(params.key) })
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
      <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        Verifying your email…
      </p>
    );
  }

  if (status === "success") {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Email verified. Redirecting…
      </p>
    );
  }

  return (
    <>
      <h1 className="mb-2 text-lg font-semibold text-foreground">Verification failed</h1>
      <Alert variant="destructive" className="mb-4">
        <AlertCircle />
        <AlertDescription>{message}</AlertDescription>
      </Alert>
      <Link href="/login" className="text-sm underline">
        Back to login
      </Link>
    </>
  );
}

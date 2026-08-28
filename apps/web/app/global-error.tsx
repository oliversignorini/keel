"use client";

import * as Sentry from "@sentry/nextjs";
import NextError from "next/error";
import { useEffect } from "react";

/**
 * App Router's own error boundary hook for errors thrown above the root
 * layout (Sentry's Next.js docs: this is the one path
 * `sentry.client.config.ts`'s automatic instrumentation doesn't already
 * cover — Next requires an explicit `global-error.tsx` to be notified at
 * all). Renders Next's own default error UI; the only addition is the
 * capture call, so that a deliberate error appears in Sentry with the
 * correct release and a readable stack.
 */
export default function GlobalError({ error }: { error: Error & { digest?: string } }) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html>
      <body>
        <NextError statusCode={0} />
      </body>
    </html>
  );
}

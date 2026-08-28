"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@keel/ui";
import { ThemeProvider, useTheme } from "next-themes";
import { useEffect, useState } from "react";

import { initPostHog } from "@/lib/posthog/client";

/** Client-only providers root layout mounts once. Split into its own
 * file so layout.tsx itself can stay a server component.
 *
 * `<Toaster>` (sonner) mounts once here — this is the contract every
 * mutation across the app calls into via `toast.success(...)` /
 * `toast.error(...)` (finding 15). */
export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());

  useEffect(() => {
    initPostHog();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
        {children}
        <ThemedToaster />
      </ThemeProvider>
    </QueryClientProvider>
  );
}

function ThemedToaster() {
  const { resolvedTheme } = useTheme();
  return <Toaster theme={resolvedTheme === "dark" ? "dark" : "light"} richColors closeButton />;
}

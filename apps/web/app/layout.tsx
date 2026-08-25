import type { Metadata } from "next";

import "./globals.css";
import { SITE_URL } from "@/lib/site";

import { Providers } from "./providers";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: "Keel",
  description: "Keel — Django + Next.js SaaS template",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // suppressHydrationWarning: next-themes sets class/data-mode on <html>
    // before hydration to avoid a flash of the wrong theme, which
    // necessarily mismatches the server-rendered markup for one attribute
    // — exactly the case next-themes' own docs say to suppress it for.
    <html lang="en" suppressHydrationWarning>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

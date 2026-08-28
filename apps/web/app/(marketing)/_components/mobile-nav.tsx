"use client";

import Link from "next/link";
import { useState } from "react";
import { MenuIcon } from "lucide-react";
import {
  Button,
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
  buttonVariants,
} from "@keel/ui";

const LINKS = [
  { href: "/pricing", label: "Pricing" },
  { href: "/blog", label: "Blog" },
  { href: "/login", label: "Log in" },
] as const;

/** The marketing header's nav below `md`, where the four links plus the
 * Sign up button no longer fit the bar (UX review finding 34). Only the
 * low-level primitives — no app-shell composite crosses the
 * `data-surface="marketing"` boundary. */
export function MarketingMobileNav() {
  const [open, setOpen] = useState(false);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open menu">
          <MenuIcon />
        </Button>
      </SheetTrigger>
      <SheetContent side="right">
        <SheetHeader>
          <SheetTitle>Menu</SheetTitle>
        </SheetHeader>
        <nav className="flex flex-col gap-1 px-4">
          {LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => setOpen(false)}
              className={buttonVariants({ variant: "ghost", className: "justify-start" })}
            >
              {link.label}
            </Link>
          ))}
          <Link
            href="/signup"
            onClick={() => setOpen(false)}
            className={buttonVariants({ className: "mt-2" })}
          >
            Sign up
          </Link>
        </nav>
      </SheetContent>
    </Sheet>
  );
}

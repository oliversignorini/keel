"use client";

import type { ReactNode } from "react";

import { useOrgContext } from "@/lib/org/org-context";

interface CanProps {
  code: string;
  children?: ReactNode;
  /** Rendered instead of nothing when the code is absent. Rarely needed —
   * most callers just want the action to not exist in the DOM. */
  fallback?: ReactNode;
}

/**
 * Renders `children` only when the current organisation's resolved
 * permission list (from `/api/v1/me/`) includes `code`.
 *
 * PRESENTATION ONLY. This component decides what to *show*, never what
 * the API will *allow* — `organizations/permissions.py`'s registry is
 * the only place authorization is expressed, and every action this hides
 * still has to pass `HasOrgPermission` server-side regardless of whether
 * the client ever rendered a control for it. See
 * lib/org/can-is-presentation-only.test.tsx, which proves exactly that by
 * calling the API directly — bypassing this component entirely — with a
 * session that lacks the code and asserting a 403.
 */
export function Can({ code, children, fallback = null }: CanProps) {
  const { currentOrg } = useOrgContext();

  if (!currentOrg?.permissions.includes(code)) {
    return <>{fallback}</>;
  }

  return <>{children}</>;
}

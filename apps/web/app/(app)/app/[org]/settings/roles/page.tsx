"use client";

import { getPermissionsRegistry, listRoles } from "@/lib/org/api";
import { useOrgContext } from "@/lib/org/org-context";
import type { RoleWithPermissions } from "@/lib/org/types";
import { useEffect, useState } from "react";

/**
 * `/app/[org]/settings/roles` (PRD §5 Routes). Read-only: the three
 * preset roles (Owner/Admin/Member — organizations/roles.py) and the
 * codes each holds, plus the full registry codes each role does NOT hold
 * so the permission surface is legible at a glance.
 *
 * Custom roles are a per-project feature flag, off by default (PRD §4
 * "Tenancy and permissions"; phase-3.md A.4) — `organizations/viewsets.py`
 * currently only wires up `list`/`retrieve` on `RoleViewSet`, no
 * create/update, which matches "off by default" exactly: there is nothing
 * to build a create-role form against yet. This page says so rather than
 * rendering a form that would 405.
 */
export default function RolesSettingsPage() {
  const { currentOrg } = useOrgContext();
  const [roles, setRoles] = useState<RoleWithPermissions[]>([]);
  const [allCodes, setAllCodes] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!currentOrg) return;
    let cancelled = false;
    Promise.all([listRoles(currentOrg.slug), getPermissionsRegistry()]).then(
      ([rolesResult, registry]) => {
        if (cancelled) return;
        setRoles(rolesResult);
        setAllCodes(registry.codes);
        setLoading(false);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [currentOrg]);

  if (!currentOrg) return null;

  return (
    <div>
      <p className="mb-6 text-sm text-neutral-600 dark:text-neutral-400">
        Custom roles aren&apos;t enabled for this project. Roles are the three built-in presets
        below.
      </p>
      {loading ? (
        <p className="text-sm text-neutral-600 dark:text-neutral-400">Loading…</p>
      ) : (
        <div className="flex flex-col gap-6">
          {roles.map((role) => (
            <section key={role.id}>
              <h2 className="mb-2 text-sm font-semibold text-neutral-900 dark:text-neutral-100">
                {role.name}
              </h2>
              <div className="flex flex-wrap gap-1.5">
                {allCodes.map((code) => (
                  <span
                    key={code}
                    className={
                      role.permissions.includes(code)
                        ? "rounded-full bg-neutral-900 px-2 py-0.5 text-xs text-white dark:bg-neutral-100 dark:text-neutral-900"
                        : "rounded-full bg-neutral-100 px-2 py-0.5 text-xs text-neutral-400 dark:bg-neutral-900 dark:text-neutral-600"
                    }
                  >
                    {code}
                  </span>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

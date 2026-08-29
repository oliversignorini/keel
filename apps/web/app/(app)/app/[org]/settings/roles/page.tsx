"use client";

import { getPermissionsRegistry, listRoles } from "@/lib/org/api";
import { useOrgContext } from "@/lib/org/org-context";
import type { RoleWithPermissions } from "@/lib/org/types";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@keel/ui";
import { Check, Minus } from "lucide-react";
import { Fragment, useEffect, useMemo, useState } from "react";

/**
 * `/app/[org]/settings/roles`. Read-only: the three
 * preset roles (Owner/Admin/Member — organizations/roles.py) and the
 * codes each holds, as a matrix — one row per permission, one column per
 * role (finding 19). The previous wall of 54 chips could not answer the
 * question the page exists to answer ("what does an Admin have that a
 * Member doesn't?") without scanning three ragged blocks; a matrix
 * answers it by reading across one line.
 *
 * Custom roles are a per-project feature flag, off by default —
 * `organizations/viewsets.py`
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

  // `resource.action` codes group cleanly by their resource half, which
  // turns a flat list of ~18 codes into a handful of labelled blocks.
  const groups = useMemo(() => grouped(allCodes), [allCodes]);

  if (!currentOrg) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Roles</CardTitle>
        <CardDescription>
          Custom roles aren&apos;t enabled for this project. Roles are the three built-in presets
          below.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex flex-col gap-3" role="status" aria-label="Loading roles">
            {[0, 1, 2, 3, 4, 5].map((row) => (
              <Skeleton key={row} className="h-6 w-full" />
            ))}
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Permission</TableHead>
                {roles.map((role) => (
                  <TableHead key={role.id} className="text-center">
                    {role.name}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {groups.map(([resource, codes]) => (
                <Fragment key={resource}>
                  <TableRow className="hover:bg-transparent">
                    <TableCell
                      colSpan={roles.length + 1}
                      className="bg-muted/50 text-xs font-semibold tracking-wide text-muted-foreground uppercase"
                    >
                      {humanise(resource)}
                    </TableCell>
                  </TableRow>
                  {codes.map((code) => (
                    <TableRow key={code}>
                      <TableCell>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="text-foreground">{actionLabel(code)}</span>
                          </TooltipTrigger>
                          <TooltipContent>
                            <code>{code}</code>
                          </TooltipContent>
                        </Tooltip>
                      </TableCell>
                      {roles.map((role) => {
                        const held = role.permissions.includes(code);
                        return (
                          <TableCell key={role.id} className="text-center">
                            {held ? (
                              <Check
                                className="mx-auto size-4 text-foreground"
                                aria-label={`${role.name} has ${code}`}
                              />
                            ) : (
                              <Minus
                                className="mx-auto size-4 text-muted-foreground"
                                aria-label={`${role.name} does not have ${code}`}
                              />
                            )}
                          </TableCell>
                        );
                      })}
                    </TableRow>
                  ))}
                </Fragment>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

/** `["members.invite", "members.remove", "billing.view"]` →
 * `[["members", [...]], ["billing", [...]]]`, each group in first-seen
 * order so the registry's own ordering survives. */
function grouped(codes: string[]): [string, string[]][] {
  const byResource = new Map<string, string[]>();
  for (const code of codes) {
    const resource = code.includes(".") ? code.slice(0, code.indexOf(".")) : code;
    const existing = byResource.get(resource);
    if (existing) existing.push(code);
    else byResource.set(resource, [code]);
  }
  return [...byResource.entries()];
}

function actionLabel(code: string): string {
  return humanise(code.includes(".") ? code.slice(code.indexOf(".") + 1) : code);
}

function humanise(segment: string): string {
  const words = segment.replace(/[._]/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

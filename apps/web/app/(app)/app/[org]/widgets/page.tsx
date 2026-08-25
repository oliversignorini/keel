"use client";

import { Can } from "@/components/org/can";
import { useOrgContext } from "@/lib/org/org-context";
import { Perm } from "@/lib/org/permissions";
import { deleteWidget, listWidgets } from "@/lib/widgets/api";
import type { Widget } from "@keel/api-client";
import { type ColumnDef, DataTable, EmptyState, PageHeader } from "@keel/ui";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

function cursorFromUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  return new URL(url).searchParams.get("cursor") ?? undefined;
}

/**
 * `/[org]/widgets` (PRD §7 demo-resource route table; docs/plans/
 * phase-6.md 6.D). The canonical `<DataTable>` usage: cursor pagination
 * (never offset — the API's `next`/`previous` are opaque URLs), row
 * selection with a permission-gated bulk action, and an empty state with
 * a primary action.
 */
export default function WidgetsPage() {
  const { currentOrg } = useOrgContext();
  const [widgets, setWidgets] = useState<Widget[]>([]);
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [history, setHistory] = useState<(string | undefined)[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(
    async (targetCursor: string | undefined) => {
      if (!currentOrg) return;
      setLoading(true);
      const page = await listWidgets(currentOrg.slug, { cursor: targetCursor });
      setWidgets(page.results);
      setNext(page.next ?? null);
      setLoading(false);
    },
    [currentOrg],
  );

  useEffect(() => {
    void load(cursor);
  }, [currentOrg, cursor, load]);

  const columns = useMemo<ColumnDef<Widget, unknown>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Name",
        cell: ({ row }) => (
          <Link
            href={`/${currentOrg?.slug}/widgets/${row.original.id}`}
            className="font-medium text-primary underline"
          >
            {row.original.name}
          </Link>
        ),
      },
      { accessorKey: "status", header: "Status" },
      { accessorKey: "description", header: "Description" },
    ],
    [currentOrg?.slug],
  );

  if (!currentOrg) return null;

  async function onBulkDelete(ids: string[], clearSelection: () => void) {
    if (!window.confirm(`Delete ${ids.length} widget(s)? This cannot be undone.`)) return;
    await Promise.all(ids.map((id) => deleteWidget(currentOrg!.slug, id)));
    clearSelection();
    await load(cursor);
  }

  const createButton = (
    <Can code={Perm.WIDGETS_MANAGE}>
      <Link
        href={`/${currentOrg.slug}/widgets/new`}
        className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground"
      >
        New widget
      </Link>
    </Can>
  );

  return (
    <div>
      <PageHeader
        title="Widgets"
        description="The reference-slice demo resource."
        actions={createButton}
      />
      <DataTable
        columns={columns}
        data={widgets}
        isLoading={loading}
        emptyState={
          <EmptyState
            title="No widgets yet"
            description="Widgets are this project's demo resource — create one to see the full CRUD slice."
            action={createButton}
          />
        }
        hasNextPage={Boolean(next)}
        hasPreviousPage={history.length > 0}
        onNextPage={() => {
          setHistory((entries) => [...entries, cursor]);
          setCursor(cursorFromUrl(next));
        }}
        onPreviousPage={() => {
          setHistory((entries) => {
            const nextHistory = entries.slice(0, -1);
            setCursor(entries.at(-1));
            return nextHistory;
          });
        }}
        bulkActions={
          currentOrg.permissions.includes(Perm.WIDGETS_MANAGE)
            ? (ids, clearSelection) => (
                <button
                  type="button"
                  onClick={() => void onBulkDelete(ids, clearSelection)}
                  className="rounded-md bg-destructive px-2 py-1 text-xs font-medium text-destructive-foreground"
                >
                  Delete
                </button>
              )
            : undefined
        }
      />
    </div>
  );
}

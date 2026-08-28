"use client";

import { Can } from "@/components/org/can";
import { useOrgContext } from "@/lib/org/org-context";
import { Perm } from "@/lib/org/permissions";
import { deleteWidget, listWidgets } from "@/lib/widgets/api";
import { widgetStatusBadgeVariant, widgetStatusLabel } from "@/lib/widgets/status";
import type { WidgetOut } from "@keel/api-client";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Badge,
  Button,
  type ColumnDef,
  DataTable,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  EmptyState,
  PageHeader,
} from "@keel/ui";
import { Box, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { WidgetsTableSkeleton } from "./_components/widgets-table-skeleton";

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
  const [widgets, setWidgets] = useState<WidgetOut[]>([]);
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [history, setHistory] = useState<(string | undefined)[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [rowPendingDelete, setRowPendingDelete] = useState<WidgetOut | null>(null);
  const [bulkPendingDelete, setBulkPendingDelete] = useState<{
    ids: string[];
    clearSelection: () => void;
  } | null>(null);

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

  const canManage = currentOrg?.permissions.includes(Perm.WIDGETS_MANAGE) ?? false;

  const columns = useMemo<ColumnDef<WidgetOut, unknown>[]>(
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
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => (
          <Badge variant={widgetStatusBadgeVariant(row.original.status)}>
            {widgetStatusLabel(row.original.status)}
          </Badge>
        ),
      },
      { accessorKey: "description", header: "Description" },
      ...(canManage
        ? [
            {
              id: "actions",
              header: "",
              enableHiding: false,
              cell: ({ row }: { row: { original: WidgetOut } }) => (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" className="size-8">
                      <MoreHorizontal />
                      <span className="sr-only">Open actions for {row.original.name}</span>
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem asChild>
                      <Link href={`/${currentOrg?.slug}/widgets/${row.original.id}`}>
                        <Pencil />
                        Edit
                      </Link>
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      variant="destructive"
                      onSelect={() => setRowPendingDelete(row.original)}
                    >
                      <Trash2 />
                      Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ),
            } satisfies ColumnDef<WidgetOut, unknown>,
          ]
        : []),
    ],
    [currentOrg?.slug, canManage],
  );

  if (!currentOrg) return null;

  async function onConfirmRowDelete() {
    if (!rowPendingDelete) return;
    const widget = rowPendingDelete;
    await deleteWidget(currentOrg!.slug, widget.id);
    setRowPendingDelete(null);
    toast.success(`${widget.name} deleted`);
    await load(cursor);
  }

  async function onConfirmBulkDelete() {
    if (!bulkPendingDelete) return;
    const { ids, clearSelection } = bulkPendingDelete;
    await Promise.all(ids.map((id) => deleteWidget(currentOrg!.slug, id)));
    setBulkPendingDelete(null);
    clearSelection();
    toast.success(`${ids.length} widget${ids.length === 1 ? "" : "s"} deleted`);
    await load(cursor);
  }

  const isEmpty = !loading && widgets.length === 0;

  const createButton = (
    <Can code={Perm.WIDGETS_MANAGE}>
      <Button asChild>
        <Link href={`/${currentOrg.slug}/widgets/new`}>New widget</Link>
      </Button>
    </Can>
  );

  return (
    <div>
      <PageHeader
        title="Widgets"
        description="The reference-slice demo resource."
        actions={isEmpty ? undefined : createButton}
      />
      {loading && widgets.length === 0 ? (
        <WidgetsTableSkeleton />
      ) : (
        <DataTable
          columns={columns}
          data={widgets}
          isLoading={loading}
          emptyState={
            <EmptyState
              icon={<Box />}
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
            canManage
              ? (ids, clearSelection) => (
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => setBulkPendingDelete({ ids, clearSelection })}
                  >
                    <Trash2 />
                    Delete
                  </Button>
                )
              : undefined
          }
        />
      )}

      <AlertDialog
        open={Boolean(rowPendingDelete)}
        onOpenChange={(open) => !open && setRowPendingDelete(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {rowPendingDelete?.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              This cannot be undone. The widget will be permanently removed.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => void onConfirmRowDelete()}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={Boolean(bulkPendingDelete)}
        onOpenChange={(open) => !open && setBulkPendingDelete(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {bulkPendingDelete?.ids.length} widgets?</AlertDialogTitle>
            <AlertDialogDescription>
              This cannot be undone. All selected widgets will be permanently removed.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => void onConfirmBulkDelete()}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

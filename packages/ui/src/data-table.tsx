"use client";

import {
  type ColumnDef,
  type RowSelectionState,
  type SortingState,
  type VisibilityState,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { type ReactNode, useMemo, useState } from "react";

import { cn } from "./cn";

export type { ColumnDef } from "@tanstack/react-table";

/** `<DataTable>` — TanStack Table wired for the shape every list page in
 * this project needs (PRD §5 component inventory; docs/plans/phase-6.md
 * 6.C): sorting, column visibility, cursor pagination (the API's `next`
 * / `previous` are opaque — this never turns them into page numbers),
 * row selection, and bulk actions. Client-side sorting is over the rows
 * already on the page, matching the API's own default ordering rather
 * than replacing it — sorting across a 50k-row table happens via the
 * cursor, not by asking the client to hold every row at once. */
export function DataTable<TData extends { id: string }>({
  columns,
  data,
  emptyState,
  bulkActions,
  hasNextPage,
  hasPreviousPage,
  onNextPage,
  onPreviousPage,
  isLoading,
}: {
  columns: ColumnDef<TData, unknown>[];
  data: TData[];
  emptyState?: ReactNode;
  bulkActions?: (selectedIds: string[], clearSelection: () => void) => ReactNode;
  hasNextPage: boolean;
  hasPreviousPage: boolean;
  onNextPage: () => void;
  onPreviousPage: () => void;
  isLoading?: boolean;
}) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});

  const table = useReactTable({
    data,
    columns,
    state: { sorting, rowSelection, columnVisibility },
    getRowId: (row) => row.id,
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    onColumnVisibilityChange: setColumnVisibility,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    enableRowSelection: Boolean(bulkActions),
  });

  const selectedIds = useMemo(() => Object.keys(rowSelection), [rowSelection]);

  if (!isLoading && data.length === 0 && emptyState) {
    return <>{emptyState}</>;
  }

  return (
    <div className="flex flex-col gap-3">
      {bulkActions && selectedIds.length > 0 ? (
        <div className="flex items-center gap-3 rounded-md border border-border bg-muted px-3 py-2 text-sm">
          <span className="text-muted-foreground">{selectedIds.length} selected</span>
          {bulkActions(selectedIds, () => setRowSelection({}))}
        </div>
      ) : null}

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="border-b border-border bg-muted/50">
                {bulkActions ? (
                  <th className="w-10 px-3 py-2">
                    <input
                      type="checkbox"
                      aria-label="Select all rows"
                      checked={table.getIsAllRowsSelected()}
                      ref={(el) => {
                        if (el) el.indeterminate = table.getIsSomeRowsSelected();
                      }}
                      onChange={table.getToggleAllRowsSelectedHandler()}
                    />
                  </th>
                ) : null}
                {headerGroup.headers.map((header) => (
                  <th key={header.id} className="px-3 py-2 text-left font-medium text-foreground">
                    {header.isPlaceholder ? null : (
                      <button
                        type="button"
                        onClick={header.column.getToggleSortingHandler()}
                        disabled={!header.column.getCanSort()}
                        className={cn(
                          "flex items-center gap-1",
                          header.column.getCanSort() && "cursor-pointer select-none",
                        )}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {{ asc: " ▲", desc: " ▼" }[header.column.getIsSorted() as string] ?? null}
                      </button>
                    )}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="border-b border-border last:border-0 hover:bg-accent/50">
                {bulkActions ? (
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      aria-label={`Select row ${row.id}`}
                      checked={row.getIsSelected()}
                      onChange={row.getToggleSelectedHandler()}
                    />
                  </td>
                ) : null}
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-3 py-2 text-foreground">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={onPreviousPage}
          disabled={!hasPreviousPage}
          className="rounded-md border border-input px-3 py-1.5 text-sm disabled:opacity-40"
        >
          Previous
        </button>
        <button
          type="button"
          onClick={onNextPage}
          disabled={!hasNextPage}
          className="rounded-md border border-input px-3 py-1.5 text-sm disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </div>
  );
}

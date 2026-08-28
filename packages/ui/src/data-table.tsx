"use client";

import {
  type ColumnDef,
  type RowSelectionState,
  type SortingState,
  type VisibilityState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { type ReactNode, useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";

import { Button } from "./components/ui/button";
import { Checkbox } from "./components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "./components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./components/ui/table";

export type { ColumnDef } from "@tanstack/react-table";

/** `<DataTable>` — TanStack Table wired for the shape every list page in
 * this project needs (PRD §5 component inventory; docs/plans/phase-6.md
 * 6.C): sorting, filtering, column visibility, cursor pagination (the
 * API's `next` / `previous` are opaque — this never turns them into
 * page numbers), row selection, and bulk actions. Client-side sorting
 * and filtering are over the rows already on the page, matching the
 * API's own default ordering rather than replacing it — reaching across
 * a 50k-row table happens via the cursor, not by asking the client to
 * hold every row at once. */
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
  filterPlaceholder = "Filter…",
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
  filterPlaceholder?: string;
}) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});
  const [globalFilter, setGlobalFilter] = useState("");

  const table = useReactTable({
    data,
    columns,
    state: { sorting, rowSelection, columnVisibility, globalFilter },
    getRowId: (row) => row.id,
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    onColumnVisibilityChange: setColumnVisibility,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    enableRowSelection: Boolean(bulkActions),
  });

  const selectedIds = useMemo(() => Object.keys(rowSelection), [rowSelection]);
  const hideableColumns = table.getAllColumns().filter((column) => column.getCanHide());

  if (!isLoading && data.length === 0 && emptyState) {
    return <>{emptyState}</>;
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <div className="relative w-full max-w-xs">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="search"
            value={globalFilter}
            onChange={(event) => setGlobalFilter(event.target.value)}
            placeholder={filterPlaceholder}
            aria-label="Filter rows"
            className="h-9 w-full rounded-md border border-input bg-background pr-8 pl-8 text-sm text-foreground shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
          />
          {globalFilter ? (
            <button
              type="button"
              onClick={() => setGlobalFilter("")}
              aria-label="Clear filter"
              className="absolute top-1/2 right-2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X className="size-4" />
            </button>
          ) : null}
        </div>

        {hideableColumns.length > 0 ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="ml-auto">
                <SlidersHorizontal />
                View
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {hideableColumns.map((column) => (
                <DropdownMenuCheckboxItem
                  key={column.id}
                  checked={column.getIsVisible()}
                  onCheckedChange={(value) => column.toggleVisibility(Boolean(value))}
                  onSelect={(event) => event.preventDefault()}
                >
                  {column.id}
                </DropdownMenuCheckboxItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </div>

      {bulkActions && selectedIds.length > 0 ? (
        <div className="flex items-center gap-3 rounded-md border border-border bg-muted px-3 py-2 text-sm">
          <span className="text-muted-foreground">{selectedIds.length} selected</span>
          {bulkActions(selectedIds, () => setRowSelection({}))}
        </div>
      ) : null}

      <div className="overflow-x-auto rounded-lg border border-border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id} className="bg-muted/50 hover:bg-muted/50">
                {bulkActions ? (
                  <TableHead className="w-10">
                    <Checkbox
                      aria-label="Select all rows"
                      checked={
                        table.getIsAllRowsSelected() ||
                        (table.getIsSomeRowsSelected() && "indeterminate")
                      }
                      onCheckedChange={(value) => table.toggleAllRowsSelected(Boolean(value))}
                    />
                  </TableHead>
                ) : null}
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id}>
                    {header.isPlaceholder ? null : (
                      <button
                        type="button"
                        onClick={header.column.getToggleSortingHandler()}
                        disabled={!header.column.getCanSort()}
                        className="flex items-center gap-1 disabled:cursor-default"
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {header.column.getCanSort()
                          ? ({
                              asc: <ArrowUp className="size-3.5" />,
                              desc: <ArrowDown className="size-3.5" />,
                            }[header.column.getIsSorted() as string] ?? (
                              <ArrowUpDown className="size-3.5 text-muted-foreground" />
                            ))
                          : null}
                      </button>
                    )}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.map((row) => (
              <TableRow key={row.id}>
                {bulkActions ? (
                  <TableCell>
                    <Checkbox
                      aria-label={`Select row ${row.id}`}
                      checked={row.getIsSelected()}
                      onCheckedChange={(value) => row.toggleSelected(Boolean(value))}
                    />
                  </TableCell>
                ) : null}
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {hasNextPage || hasPreviousPage ? (
        <div className="flex items-center justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onPreviousPage} disabled={!hasPreviousPage}>
            <ChevronLeft />
            Previous
          </Button>
          <Button variant="outline" size="sm" onClick={onNextPage} disabled={!hasNextPage}>
            Next
            <ChevronRight />
          </Button>
        </div>
      ) : null}
    </div>
  );
}

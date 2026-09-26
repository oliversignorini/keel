import { Skeleton } from "@keel/ui";

/** Shaped like the widgets table — filter bar, header row, five body
 * rows — instead of a bare "Loading…" string. */
export function WidgetsTableSkeleton() {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <div className="h-9 w-full max-w-xs">
          <Skeleton />
        </div>
        <div className="ml-auto h-9 w-20">
          <Skeleton />
        </div>
      </div>
      <div className="overflow-hidden rounded-lg border border-border">
        <div className="flex items-center gap-4 border-b border-border bg-muted/50 px-4 py-2.5">
          <div className="h-4 w-24">
            <Skeleton />
          </div>
          <div className="h-4 w-16">
            <Skeleton />
          </div>
          <div className="h-4 w-40">
            <Skeleton />
          </div>
        </div>
        {Array.from({ length: 5 }).map((_, index) => (
          <div
            key={index}
            className="flex items-center gap-4 border-b border-border px-4 py-3 last:border-b-0"
          >
            <div className="h-4 w-32">
              <Skeleton />
            </div>
            <div className="h-5 w-16">
              <Skeleton shape="pill" />
            </div>
            <div className="h-4 w-56">
              <Skeleton />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

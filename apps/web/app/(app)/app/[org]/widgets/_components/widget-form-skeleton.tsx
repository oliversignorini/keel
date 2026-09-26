import { Skeleton } from "@keel/ui";

/** Shaped like `<ResourceForm>` — a card with labeled fields and a footer
 * button — instead of blanking to nothing while the widget loads. */
export function WidgetFormSkeleton() {
  return (
    <div className="flex flex-col gap-4 rounded-lg border border-border p-6">
      {Array.from({ length: 3 }).map((_, index) => (
        <div key={index} className="flex flex-col gap-1.5">
          <div className="h-4 w-16">
            <Skeleton />
          </div>
          <div className="h-9 w-full">
            <Skeleton />
          </div>
        </div>
      ))}
      <div className="flex justify-end">
        <div className="h-9 w-32">
          <Skeleton />
        </div>
      </div>
    </div>
  );
}

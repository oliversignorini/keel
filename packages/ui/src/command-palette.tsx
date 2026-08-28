"use client";

import { useMemo } from "react";

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem as CommandItemPrimitive,
  CommandList,
  CommandShortcut,
} from "./components/ui/command";

export interface CommandItem {
  id: string;
  label: string;
  group?: string;
  shortcut?: string;
  onSelect: () => void;
}

/** `<CommandPalette>` — ⌘K navigation, resource search, and actions
 * (PRD §5 component inventory; docs/plans/phase-6.md 6.C: "Must be fully
 * keyboard-reachable — it is a first-class navigation path per the
 * accessibility floor, not a power-user extra").
 *
 * Built on shadcn's `<Command>` (cmdk) — correct listbox ARIA by
 * construction (finding 8). The caller still owns what `items` *are*
 * (static nav entries, plus whatever a resource search against `query`
 * resolves to) via `onQueryChange`, and cmdk's own substring filter is
 * disabled (`shouldFilter={false}`) so a slow network search isn't
 * second-guessed by client-side filtering.
 */
export function CommandPalette({
  open,
  onOpenChange,
  items,
  query,
  onQueryChange,
  placeholder = "Search or jump to…",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  items: CommandItem[];
  query: string;
  onQueryChange: (query: string) => void;
  placeholder?: string;
}) {
  const grouped = useMemo(() => {
    const groups = new Map<string, CommandItem[]>();
    for (const item of items) {
      const key = item.group ?? "";
      const bucket = groups.get(key) ?? [];
      bucket.push(item);
      groups.set(key, bucket);
    }
    return groups;
  }, [items]);

  return (
    <CommandDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Command palette"
      description={placeholder}
      shouldFilter={false}
    >
      <CommandInput value={query} onValueChange={onQueryChange} placeholder={placeholder} />
      <CommandList>
        <CommandEmpty>No results.</CommandEmpty>
        {[...grouped.entries()].map(([group, groupItems]) => (
          <CommandGroup key={group || "ungrouped"} heading={group || undefined}>
            {groupItems.map((item) => (
              <CommandItemPrimitive
                key={item.id}
                value={item.id}
                onSelect={() => {
                  onOpenChange(false);
                  item.onSelect();
                }}
              >
                <span>{item.label}</span>
                {item.shortcut ? <CommandShortcut>{item.shortcut}</CommandShortcut> : null}
              </CommandItemPrimitive>
            ))}
          </CommandGroup>
        ))}
      </CommandList>
    </CommandDialog>
  );
}

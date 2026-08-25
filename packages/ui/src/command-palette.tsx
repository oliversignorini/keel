"use client";

import { type KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";

import { cn } from "./cn";

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
 * Owns the query string and the active-item index; the caller owns what
 * `items` *are* (static nav entries, plus whatever a resource search
 * against `query` resolves to) via `onQueryChange`, so a slow network
 * search doesn't block the keyboard interaction this component is
 * responsible for.
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
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setActiveIndex(0);
      // Autofocus is deliberate: opening the palette (⌘K) IS the request
      // for keyboard input, the same way a browser's own address bar
      // focuses itself on Ctrl+L.
      inputRef.current?.focus();
    }
  }, [open]);

  useEffect(() => {
    setActiveIndex(0);
  }, [items]);

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

  if (!open) return null;

  function select(item: CommandItem | undefined) {
    if (!item) return;
    onOpenChange(false);
    item.onSelect();
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      onOpenChange(false);
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => Math.min(index + 1, items.length - 1));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => Math.max(index - 1, 0));
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      select(items[activeIndex]);
    }
  }

  let flatIndex = -1;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 pt-[15vh]"
      onClick={() => onOpenChange(false)}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="w-full max-w-lg overflow-hidden rounded-lg border border-border bg-popover shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <input
          ref={inputRef}
          role="combobox"
          aria-expanded="true"
          aria-controls="command-palette-list"
          aria-activedescendant={
            items[activeIndex] ? `command-item-${items[activeIndex].id}` : undefined
          }
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          className="w-full border-b border-border bg-transparent px-4 py-3 text-sm text-foreground outline-none"
        />
        <ul id="command-palette-list" role="listbox" className="max-h-80 overflow-y-auto py-1">
          {items.length === 0 ? (
            <li className="px-4 py-6 text-center text-sm text-muted-foreground">No results.</li>
          ) : (
            [...grouped.entries()].map(([group, groupItems]) => (
              <li key={group || "ungrouped"}>
                {group ? (
                  <div className="px-4 pt-2 pb-1 text-xs font-medium text-muted-foreground">
                    {group}
                  </div>
                ) : null}
                <ul>
                  {groupItems.map((item) => {
                    flatIndex += 1;
                    const isActive = flatIndex === activeIndex;
                    return (
                      <li key={item.id}>
                        <button
                          id={`command-item-${item.id}`}
                          type="button"
                          role="option"
                          aria-selected={isActive}
                          onMouseEnter={() => setActiveIndex(flatIndex)}
                          onClick={() => select(item)}
                          className={cn(
                            "flex w-full items-center justify-between px-4 py-2 text-left text-sm",
                            isActive ? "bg-accent text-accent-foreground" : "text-foreground",
                          )}
                        >
                          <span>{item.label}</span>
                          {item.shortcut ? (
                            <span className="text-xs text-muted-foreground">{item.shortcut}</span>
                          ) : null}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}

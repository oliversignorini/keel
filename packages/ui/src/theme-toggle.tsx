/** Presentational only — dark mode itself is `next-themes` (apps/web),
 * not a dependency of this package. `isDark` / `onToggle` are the only
 * seam this component needs. */
export function ThemeToggleButton({ isDark, onToggle }: { isDark: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      className="rounded-md p-1.5 text-foreground hover:bg-accent"
    >
      <span aria-hidden="true">{isDark ? "☀" : "◐"}</span>
    </button>
  );
}

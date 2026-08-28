"use client";

import { MonitorIcon, MoonIcon, SunIcon } from "lucide-react";

import { Button } from "./components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "./components/ui/dropdown-menu";

export type ThemePreference = "light" | "dark" | "system";

type ThemeToggleButtonProps =
  | {
      /** @deprecated pass `theme`/`setTheme` for the three-way Light/Dark/System control. */
      isDark: boolean;
      onToggle: () => void;
      theme?: undefined;
      setTheme?: undefined;
    }
  | {
      theme: ThemePreference;
      setTheme: (theme: ThemePreference) => void;
      isDark?: undefined;
      onToggle?: undefined;
    };

/** Presentational only — dark mode itself is `next-themes` (apps/web),
 * not a dependency of this package. Pass `theme`/`setTheme` for the
 * three-way Light/Dark/System dropdown (finding 1); the legacy
 * `isDark`/`onToggle` binary toggle is still supported so existing call
 * sites keep compiling unchanged. */
export function ThemeToggleButton(props: ThemeToggleButtonProps) {
  if (props.setTheme) {
    const { theme, setTheme } = props;
    const Icon = theme === "dark" ? MoonIcon : theme === "light" ? SunIcon : MonitorIcon;

    return (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button type="button" variant="ghost" size="icon" aria-label="Change theme">
            <Icon className="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={() => setTheme("light")}>
            <SunIcon />
            Light
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => setTheme("dark")}>
            <MoonIcon />
            Dark
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => setTheme("system")}>
            <MonitorIcon />
            System
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    );
  }

  const { isDark, onToggle } = props;

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      onClick={onToggle}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
    >
      {isDark ? <MoonIcon className="size-4" /> : <SunIcon className="size-4" />}
    </Button>
  );
}

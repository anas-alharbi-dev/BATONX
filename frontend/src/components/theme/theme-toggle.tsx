"use client";

import { DesktopIcon, MoonIcon, SunIcon } from "@radix-ui/react-icons";

import { useTheme, type ThemePreference } from "./theme-provider";

const OPTIONS: { id: ThemePreference; label: string; Icon: typeof SunIcon }[] = [
  { id: "system", label: "Use system theme", Icon: DesktopIcon },
  { id: "light", label: "Light theme", Icon: SunIcon },
  { id: "dark", label: "Dark theme", Icon: MoonIcon },
];

/**
 * A 3-way segmented control (system / light / dark), not a single toggle —
 * the preference is tri-state and the current UI needs to say so honestly
 * rather than collapsing "system" into a guess. Preference persists to
 * localStorage only (see theme-provider.tsx) — no account, no backend yet.
 */
export function ThemeToggle() {
  const { preference, setPreference } = useTheme();

  return (
    <div
      role="radiogroup"
      aria-label="Theme"
      className="inline-flex items-center gap-0.5 rounded-md border border-line bg-surface p-0.5"
    >
      {OPTIONS.map(({ id, label, Icon }) => {
        const active = preference === id;
        return (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={label}
            title={label}
            onClick={() => setPreference(id)}
            className={
              "grid size-7 place-items-center rounded-[5px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent " +
              (active
                ? "bg-surface-raised text-fg"
                : "text-fg-subtle hover:text-fg-muted")
            }
          >
            <Icon className="size-3.5" aria-hidden />
          </button>
        );
      })}
    </div>
  );
}

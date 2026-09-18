"use client";

import { useLanguage } from "@/lib/i18n";
import type { Locale } from "@/lib/i18n";

const OPTIONS: { id: Locale; short: string }[] = [
  { id: "en", short: "EN" },
  { id: "ar", short: "AR" },
];

/**
 * Compact EN/العربية switcher — mirrors `ThemeToggle`'s exact segmented-
 * control pattern so the two preference controls read as one family.
 * Deliberately small: two letters, no flag icons (a flag implies a country,
 * not a language), never the dominant element in whatever bar hosts it.
 */
export function LanguageSwitcher() {
  const { locale, dict, setLocale } = useLanguage();

  return (
    <div
      role="radiogroup"
      aria-label={dict.language.label}
      className="inline-flex items-center gap-0.5 rounded-md border border-line bg-surface p-0.5"
    >
      {OPTIONS.map(({ id, short }) => {
        const active = locale === id;
        const label = id === "en" ? dict.language.en : dict.language.ar;
        return (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={label}
            title={label}
            onClick={() => setLocale(id)}
            className={
              "rounded-[5px] px-1.5 py-1 font-mono text-[11px] font-medium tracking-wide transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent " +
              (active
                ? "bg-surface-raised text-fg"
                : "text-fg-subtle hover:text-fg-muted")
            }
          >
            {short}
          </button>
        );
      })}
    </div>
  );
}

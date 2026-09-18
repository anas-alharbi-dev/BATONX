/**
 * Localization foundation (Phase P-7). Two languages only — English (default)
 * and Arabic — no heavyweight i18n framework: a flat dictionary keyed by
 * dot-path string, a `t()` lookup with an always-safe English fallback, and
 * a provider that mirrors `theme-provider.tsx`'s exact pattern (localStorage
 * preference, a blocking pre-paint script, no backend dependency).
 */
export type Locale = "en" | "ar";

export const LOCALES: Locale[] = ["en", "ar"];

export const DEFAULT_LOCALE: Locale = "en";

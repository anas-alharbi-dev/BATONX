/**
 * Public surface of the localization module. Components read strings via the
 * typed `dict` object from `useLanguage()` (e.g. `dict.proposal.reject`) —
 * no dot-path string keys, no runtime "key not found" — TypeScript itself
 * guarantees `ar.ts` and `en.ts` share the same shape (see `Dictionary` in
 * `en.ts`). `interpolate` fills the handful of strings that carry a `{var}`
 * placeholder (a timestamp, a file path).
 */
export { LanguageProvider, useLanguage, languageInitScript } from "./language-provider";
export type { Locale } from "./types";
export type { Dictionary } from "./en";

export function interpolate(template: string, vars: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (match, key) => vars[key] ?? match);
}

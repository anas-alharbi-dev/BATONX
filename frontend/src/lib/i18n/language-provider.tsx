"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import en, { type Dictionary } from "./en";
import ar from "./ar";
import { DEFAULT_LOCALE, type Locale } from "./types";

const STORAGE_KEY = "batonx:locale";

const DICTIONARIES: Record<Locale, Dictionary> = { en, ar };
const DIR: Record<Locale, "ltr" | "rtl"> = { en: "ltr", ar: "rtl" };

interface LanguageContextValue {
  locale: Locale;
  dir: "ltr" | "rtl";
  dict: Dictionary;
  setLocale: (locale: Locale) => void;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

function readStoredLocale(): Locale {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === "en" || raw === "ar") return raw;
  } catch {
    /* ignore — private mode / blocked storage */
  }
  return DEFAULT_LOCALE;
}

function applyLocale(locale: Locale) {
  document.documentElement.setAttribute("lang", locale);
  document.documentElement.setAttribute("dir", DIR[locale]);
}

/**
 * Language preference: en | ar, persisted client-side only (localStorage —
 * no backend dependency, mirroring `theme-provider.tsx`'s exact pattern).
 * The initial `dir`/`lang` are stamped synchronously before hydration by the
 * inline script in the root layout (see `languageInitScript`), so there is
 * no flash of the wrong direction; this provider takes over for live
 * updates (the language switcher).
 */
export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(DEFAULT_LOCALE);

  useEffect(() => {
    const stored = readStoredLocale();
    setLocaleState(stored);
    applyLocale(stored);
  }, []);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore */
    }
    applyLocale(next);
  }, []);

  const value = useMemo(
    () => ({ locale, dir: DIR[locale], dict: DICTIONARIES[locale], setLocale }),
    [locale, setLocale],
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageContextValue {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error("useLanguage must be used within LanguageProvider");
  return ctx;
}

/**
 * Inlined verbatim as a blocking <script> at the top of <head>, right after
 * `themeInitScript` — stamps `lang`/`dir` on <html> before first paint, from
 * the stored preference (English if none). Prevents a flash of LTR-then-RTL
 * (or vice versa) on load/reload.
 */
export const languageInitScript = `(function(){try{
  var KEY="${STORAGE_KEY}";
  var loc=localStorage.getItem(KEY);
  if(loc!=="en"&&loc!=="ar"){loc="en";}
  document.documentElement.setAttribute("lang", loc);
  document.documentElement.setAttribute("dir", loc==="ar"?"rtl":"ltr");
}catch(e){document.documentElement.setAttribute("lang","en");document.documentElement.setAttribute("dir","ltr");}})();`;
